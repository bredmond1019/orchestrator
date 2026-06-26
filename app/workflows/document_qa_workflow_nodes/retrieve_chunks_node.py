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
from sqlalchemy import func, or_

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
        "is_section_title_field": "is_section_title",  # was None — now wired
        # FTS column: a generated, weighted tsvector over title+keywords ('A'),
        # description ('B'), content ('C'). Its presence switches the keyword
        # stage from binary ILIKE to graded ts_rank (see _keyword_search).
        "tsv_field": "content_tsv",
        "filter_fields": {
            "layer": "array",
            "project": "scalar",
            "status": "scalar",
        },
        # Exclude archived docs from default retrieval; override with
        # include_archived=True (an explicit DocumentQAEventSchema field).
        "default_status_exclude": "archived",
    },
}

# Keyword fusion weights (tune against the Block H smoke queries):
# - _KW_WEIGHT scales the graded FTS ts_rank contribution (ts_rank values are
#   small, typically < 0.1, so this is larger than the legacy flat boost).
# - _KW_BOOST is the legacy flat boost for the ILIKE-set ("content") corpus,
#   preserved unchanged at 1.0 so that path is regression-free.
_KW_WEIGHT: float = 5.0
_KW_BOOST: float = 1.0


def _apply_metadata_filters(query, model, filters: dict, filter_fields: dict):
    """Apply optional metadata WHERE clauses to a SQLAlchemy query.

    For each ``{field: value}`` pair in ``filters``, looks up the declared type
    in ``filter_fields`` and appends the appropriate clause: ``==`` for scalars,
    ``.overlap([value])`` for arrays. Unknown fields and ``None`` values are
    silently skipped so callers don't need to pre-sanitize.

    Returns the (possibly modified) query object.
    """
    for field, value in filters.items():
        if value is None or field not in filter_fields:
            continue
        col = getattr(model, field, None)
        if col is None:
            continue
        if filter_fields[field] == "array":
            query = query.filter(col.overlap([value]))
        else:
            query = query.filter(col == value)
    return query


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
        # Provenance / citation fields (None for corpora that lack them, e.g. content_chunks).
        "file_path": getattr(row, "file_path", None),
        "doc_id": getattr(row, "doc_id", None),
        "title": getattr(row, "title", None),
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
        filters = getattr(event, "filters", None)
        include_archived = getattr(event, "include_archived", False)
        chunks = self.retrieve(
            query,
            corpus=corpus,
            k=5,
            filters=filters,
            include_archived=include_archived,
        )
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
        *,
        filters: dict | None = None,
        include_archived: bool = False,
    ) -> list[dict]:
        """Run the two-stage hybrid retrieval pipeline.

        Args:
            query: The user question text to search over.
            corpus: Corpus to query — ``"content"`` (content_chunks) or
                ``"brain"`` (brain_documents).
            k: Maximum number of chunks to return.
            threshold: Minimum fused score to include a chunk in results.
            filters: Optional metadata WHERE clauses (brain corpus only).
            include_archived: When False (default), brain-corpus results exclude
                docs with ``status="archived"``.

        Returns:
            List of up to ``k`` normalized chunk dicts, each containing
            ``{"content", "section_title", "score", "source", "file_path",
            "doc_id", "title"}``, sorted by fused score descending.
        """
        vector = EmbeddingService().embed_text(query)
        candidates = self._semantic_search(
            vector, corpus, limit=20, filters=filters, include_archived=include_archived
        )
        candidate_ids = [c["id"] for c in candidates]
        keyword_matches = self._keyword_search(query, candidate_ids, corpus)
        return self._fuse_and_rank(candidates, keyword_matches, k, threshold)

    def _semantic_search(
        self,
        vector: list[float],
        corpus: str,
        limit: int,
        filters: dict | None = None,
        include_archived: bool = False,
    ) -> list[dict]:
        """Stage 1: pgvector cosine-distance query returning a wide candidate set.

        Queries the corpus table ordered by cosine distance to ``vector``, up
        to ``limit`` rows. When ``filters`` is provided and the corpus declares
        ``filter_fields``, applies WHERE clauses before ordering — scalar fields
        use ``==``; array fields (e.g. ``layer``) use ``.overlap([value])``.
        Unknown filter keys and corpora without ``filter_fields`` are silently
        ignored so ``"content"`` remains unaffected.

        Returns a list of candidate dicts with keys:
        ``id``, ``content``, ``section_title``, ``is_section_title``,
        ``distance``.

        This method is isolated so tests can patch it without a live DB.
        """
        config = _CORPUS_CONFIG[corpus]
        model = config["model"]
        with contextmanager(db_session)() as session:
            distance_expr = model.embedding.cosine_distance(vector)
            q = session.query(model, distance_expr.label("_distance"))
            if filters and config.get("filter_fields"):
                q = _apply_metadata_filters(
                    q, model, filters, config["filter_fields"]
                )
            # Default: exclude archived docs unless the caller opts in. A NULL
            # status is kept (only an explicit "archived" is filtered).
            exclude = config.get("default_status_exclude")
            if exclude and not include_archived:
                status_col = getattr(model, "status", None)
                if status_col is not None:
                    q = q.filter(
                        (status_col != exclude) | (status_col.is_(None))
                    )
            rows = q.order_by(distance_expr).limit(limit).all()
            return [_row_to_candidate(row, distance, config) for row, distance in rows]

    def _keyword_search(
        self,
        query: str,
        candidate_ids: list,
        corpus: str,
    ) -> set | dict:
        """Stage 2: keyword re-rank scoped to stage-1 candidate IDs.

        Two paths, selected by whether the corpus declares a ``tsv_field``:

        - **FTS path** (brain corpus): a single ranked Postgres full-text query
          against the generated ``content_tsv`` column. Returns a
          ``dict[id -> ts_rank]`` — a *graded* signal where a query term in a
          doc's title (setweight 'A') outranks the same term in body text
          (setweight 'C'). ``plainto_tsquery`` strips English stop words and
          stems natively, so no manual term/stop-word handling is needed.
        - **Legacy ILIKE path** (content corpus): binary substring match
          returning a ``set[id]`` of candidates that matched at least one term.

        Scoped to ``candidate_ids`` so only Stage-1 candidates are re-ranked.
        Isolated so tests can patch it without a live DB.
        """
        config = _CORPUS_CONFIG[corpus]
        tsv_field = config.get("tsv_field")

        if not candidate_ids:
            return {} if tsv_field else set()

        if tsv_field:
            return self._keyword_search_fts(query, candidate_ids, config, tsv_field)
        return self._keyword_search_ilike(query, candidate_ids, config)

    @staticmethod
    def _keyword_search_fts(
        query: str, candidate_ids: list, config: dict, tsv_field: str
    ) -> dict:
        """Graded full-text search: returns ``dict[id -> ts_rank]`` (FTS corpora)."""
        model = config["model"]
        tsv_col = getattr(model, tsv_field)
        tsquery = func.plainto_tsquery("english", query)
        rank = func.ts_rank(tsv_col, tsquery)
        with contextmanager(db_session)() as session:
            q = (
                session.query(model.id, rank.label("kw_rank"))
                .filter(model.id.in_(candidate_ids))
                .filter(tsv_col.op("@@")(tsquery))
            )
            return {row.id: float(row.kw_rank) for row in q.all()}

    @staticmethod
    def _keyword_search_ilike(query: str, candidate_ids: list, config: dict) -> set:
        """Legacy binary substring match: returns ``set[id]`` (content corpus)."""
        model = config["model"]
        content_col = getattr(model, config["content_field"])
        terms = [t for t in (re.sub(r"\W+", "", w) for w in query.split()) if t]
        if not terms:
            return set()

        ilike_filters = [content_col.ilike(f"%{t}%") for t in terms]
        for extra_field in config.get("keyword_extra_fields", []):
            extra_col = getattr(model, extra_field, None)
            if extra_col is None:
                continue
            ilike_filters.extend(
                func.array_to_string(extra_col, " ").ilike(f"%{t}%") for t in terms
            )

        with contextmanager(db_session)() as session:
            q = (
                session.query(model.id)
                .filter(model.id.in_(candidate_ids))
                .filter(or_(*ilike_filters))
            )
            return {row.id for row in q.all()}

    def _fuse_and_rank(
        self,
        candidates: list[dict],
        keyword_matches: set | dict,
        k: int,
        threshold: float,
    ) -> list[dict]:
        """Pure score fusion, NaN filtering, and top-k selection.

        Score formula (ported from rag-engine-rs ``two_stage_retrieval.rs``):

            score = (1.0 - distance) * (2.0 if is_section_title else 1.0)
                    + keyword_contribution

        The keyword contribution depends on the shape of ``keyword_matches``:

        - ``dict[id -> ts_rank]`` (FTS corpora): graded —
          ``_KW_WEIGHT * ts_rank``. A stronger / better-weighted match scores
          higher than a weak one.
        - ``set[id]`` (legacy ILIKE corpora): flat ``_KW_BOOST`` for membership.

        NaN-safe: candidates whose ``distance`` is NaN are filtered out before
        sorting (the Rust ``total_cmp`` guard, which never panics on NaN).

        Args:
            candidates: Stage-1 candidates with ``id``, ``distance``,
                ``is_section_title``, ``content``, ``section_title`` keys.
            keyword_matches: Either a ``dict[id -> ts_rank]`` (graded FTS) or a
                ``set[id]`` (legacy binary) of keyword hits.
            k: Maximum number of results to return.
            threshold: Minimum fused score to include a result.

        Returns:
            List of normalized dicts ``{"content", "section_title", "score",
            "source", "file_path", "doc_id", "title"}`` sorted by score
            descending, length <= ``k``.
        """
        graded = isinstance(keyword_matches, dict)
        scored = []
        for c in candidates:
            distance = c["distance"]
            # NaN guard — replicate Rust total_cmp; skip NaN distances
            if math.isnan(distance):
                continue
            similarity = 1.0 - distance
            title_weight = 2.0 if c.get("is_section_title") else 1.0
            if graded:
                keyword_boost = _KW_WEIGHT * keyword_matches.get(c["id"], 0.0)
            else:
                keyword_boost = _KW_BOOST if c["id"] in keyword_matches else 0.0
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
                    # Provenance / citation fields (carried through from candidates).
                    "file_path": c.get("file_path"),
                    "doc_id": c.get("doc_id"),
                    "title": c.get("title"),
                }
            )

        scored.sort(key=lambda c: c["score"], reverse=True)
        return scored[:k]
