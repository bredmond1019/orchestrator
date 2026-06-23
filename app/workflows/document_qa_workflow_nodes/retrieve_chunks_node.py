"""RetrieveChunksNode — two-stage hybrid retrieval for RAG queries.

Implements the semantic-then-keyword re-rank pattern ported from the
rag-engine-rs two-stage retrieval service (``two_stage_retrieval.rs`` and
``query.rs``). Three ideas carried over:

1. **Semantic → keyword scoped re-rank with additive score fusion**: Stage 1
   runs pgvector cosine-distance to fetch a wide candidate set (top-20); Stage
   2 runs keyword ILIKE scoped to those candidate IDs; scores are fused
   additively.
2. **Section-title chunk weighting**: chunks flagged ``is_section_title=True``
   receive a 2x multiplier on their semantic similarity component
   (``process_results`` pattern from ``query.rs``).
3. **Assembled context includes source title + relevance score** per chunk —
   consumed by ``AssembleContextNode`` in the query workflow.

Supports two corpora:
- ``"content"`` — queries the ``content_chunks`` table (documents ingested by
  this project, the default Q&A path).
- ``"brain"`` — queries the ``brain_documents`` table (the agentic-portfolio
  company brain corpus, for brain-RAG integration).

The corpus dispatch is a small mapping so adding a third corpus is a one-line
addition. DB calls are isolated in ``_semantic_search`` and ``_keyword_search``
(mockable seams); ``_fuse_and_rank`` is pure and unit-testable without a DB.
"""

import math
import re
from contextlib import contextmanager

from core.nodes.base import Node
from core.task import TaskContext
from database.brain_document import BrainDocument
from database.content_chunk import ContentChunk
from database.session import db_session
from services.embedding_service import EmbeddingService
from sqlalchemy import or_

# ---------------------------------------------------------------------------
# Corpus configuration map — extend here to add a third corpus
# ---------------------------------------------------------------------------

_CORPUS_CONFIG: dict[str, dict] = {
    "content": {
        "model": ContentChunk,
        "content_field": "content",
        "section_title_field": "section_title",
        "is_section_title_field": "is_section_title",
    },
    "brain": {
        "model": BrainDocument,
        "content_field": "content",
        "section_title_field": "section",
        "is_section_title_field": None,
    },
}


def _row_to_candidate(row, distance: float, config: dict) -> dict:
    """Convert one ORM row + its cosine distance into a normalized candidate dict."""
    stf = config["section_title_field"]
    istf = config["is_section_title_field"]
    return {
        "id": row.id,
        "content": getattr(row, config["content_field"]),
        "section_title": getattr(row, stf, None),
        "is_section_title": bool(getattr(row, istf, False)) if istf else False,
        "distance": float(distance),
    }


class RetrieveChunksNode(Node):
    """Two-stage hybrid retrieval node.

    Stage 1: semantic candidate set via pgvector cosine distance (top-20).
    Stage 2: keyword re-rank via ILIKE scoped to stage-1 candidate IDs.
    Score fusion: semantic similarity + keyword boost + section-title 2x weight.

    Build carefully — this node is reused verbatim by downstream workflows.
    """

    def process(self, task_context: TaskContext) -> TaskContext:
        """Run two-stage retrieval and store results in the task context."""
        event = task_context.event
        query = event.question
        corpus = getattr(event, "corpus", "content")
        chunks = self.retrieve(query, corpus=corpus, k=5)
        task_context.update_node(
            node_name=self.node_name,
            result={"chunks": chunks},
        )
        return task_context

    def retrieve(
        self,
        query: str,
        corpus: str = "content",
        k: int = 5,
        threshold: float = 0.0,
    ) -> list[dict]:
        """Run the two-stage hybrid retrieval pipeline.

        Args:
            query: The user question text to search over.
            corpus: Corpus to query — ``"content"`` (content_chunks) or
                ``"brain"`` (brain_documents).
            k: Maximum number of chunks to return.
            threshold: Minimum fused score to include a chunk in results.

        Returns:
            List of up to ``k`` normalized chunk dicts, each containing
            ``{"content", "section_title", "score", "source"}``, sorted by
            fused score descending.
        """
        vector = EmbeddingService().embed_text(query)
        candidates = self._semantic_search(vector, corpus, limit=20)
        candidate_ids = [c["id"] for c in candidates]
        keyword_ids = self._keyword_search(query, candidate_ids, corpus)
        return self._fuse_and_rank(candidates, keyword_ids, k, threshold)

    def _semantic_search(
        self,
        vector: list[float],
        corpus: str,
        limit: int,
    ) -> list[dict]:
        """Stage 1: pgvector cosine-distance query returning a wide candidate set.

        Queries the corpus table ordered by cosine distance to ``vector``, up
        to ``limit`` rows. Returns a list of candidate dicts with keys:
        ``id``, ``content``, ``section_title``, ``is_section_title``,
        ``distance``.

        This method is isolated so tests can patch it without a live DB.
        """
        config = _CORPUS_CONFIG[corpus]
        model = config["model"]
        with contextmanager(db_session)() as session:
            distance_expr = model.embedding.cosine_distance(vector)
            rows = (
                session.query(model, distance_expr.label("_distance"))
                .order_by(distance_expr)
                .limit(limit)
                .all()
            )
            return [_row_to_candidate(row, distance, config) for row, distance in rows]

    def _keyword_search(
        self,
        query: str,
        candidate_ids: list,
        corpus: str,
    ) -> set:
        """Stage 2: ILIKE keyword match scoped to stage-1 candidate IDs.

        Returns the set of candidate IDs whose content field contains at least
        one query term as a substring (case-insensitive). Scoped to
        ``candidate_ids`` so only candidates from Stage 1 are re-ranked.

        This method is isolated so tests can patch it without a live DB.
        """
        if not candidate_ids:
            return set()

        config = _CORPUS_CONFIG[corpus]
        model = config["model"]
        content_field = config["content_field"]
        content_col = getattr(model, content_field)

        terms = [re.sub(r"\W+", "", t) for t in query.split()]
        terms = [t for t in terms if t]
        if not terms:
            return set()

        with contextmanager(db_session)() as session:
            ilike_filters = [content_col.ilike(f"%{term}%") for term in terms]
            q = (
                session.query(model.id)
                .filter(model.id.in_(candidate_ids))
                .filter(or_(*ilike_filters))
            )
            matching_ids = {row.id for row in q.all()}

        return matching_ids

    def _fuse_and_rank(
        self,
        candidates: list[dict],
        keyword_ids: set,
        k: int,
        threshold: float,
    ) -> list[dict]:
        """Pure score fusion, NaN filtering, and top-k selection.

        Score formula (ported from rag-engine-rs ``two_stage_retrieval.rs``):

            score = (1.0 - distance) * (2.0 if is_section_title else 1.0)
                    + (1.0 if id in keyword_ids else 0.0)

        NaN-safe: candidates whose ``distance`` is NaN are filtered out before
        sorting (the Rust ``total_cmp`` guard, which never panics on NaN).

        Args:
            candidates: Stage-1 candidates with ``id``, ``distance``,
                ``is_section_title``, ``content``, ``section_title`` keys.
            keyword_ids: Set of candidate IDs that matched the keyword filter.
            k: Maximum number of results to return.
            threshold: Minimum fused score to include a result.

        Returns:
            List of normalized dicts ``{"content", "section_title", "score",
            "source"}`` sorted by score descending, length <= ``k``.
        """
        scored = []
        for c in candidates:
            distance = c["distance"]
            # NaN guard — replicate Rust total_cmp; skip NaN distances
            if math.isnan(distance):
                continue
            similarity = 1.0 - distance
            title_weight = 2.0 if c.get("is_section_title") else 1.0
            keyword_boost = 1.0 if c["id"] in keyword_ids else 0.0
            score = similarity * title_weight + keyword_boost
            if score < threshold:
                continue
            scored.append(
                {
                    "id": c["id"],
                    "content": c["content"],
                    "section_title": c.get("section_title"),
                    "score": score,
                    "source": c.get("section_title") or "General",
                }
            )

        scored.sort(key=lambda c: c["score"], reverse=True)
        return scored[:k]
