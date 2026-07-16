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
  company brain corpus, for brain-RAG integration). Adds a Stage 1b
  structural neighborhood-expansion: the ``related:``-neighbors (from
  ``brain_edges``, mev's ``emit-graph`` output) of the top Stage-1 semantic
  hits are pulled in as extra candidates before keyword re-rank, flagged
  ``via="structural"`` for explainability (OR.G). Also adds a Stage 1c
  keyword-candidate expansion: an independent top-K full-text query (ordered
  by ``ts_rank``, same corpus/filters/archived-exclusion as
  ``_semantic_search``) whose hits are unioned into the candidate set flagged
  ``via="keyword"``, so a document with a strong keyword match but a weak
  cosine-distance rank still gets scored by Stage 2 keyword re-rank instead
  of being invisible to it.

Also adds a Stage 1d memory expansion: when the caller opts in
(``include_memory=True``) with a non-None ``workspace_id``, accumulated
``SemanticMemory`` facts (``app/memory/``, block OR.S) scoped to that
workspace/peer are pulled in via ``MemoryLoaderNode.retrieve()`` (cosine mode,
reusing the Stage-1 query embedding) and merged in as candidates flagged
``via="memory"``. Decay is applied in the adapter (see ``_memory_expand``)
since cosine mode itself applies none. Gated independently of corpus — it
runs for any corpus, not just "brain".

The corpus dispatch is a small mapping so adding a third corpus is a one-line
addition. DB calls are isolated in ``_semantic_search``, ``_structural_expand``,
``_keyword_expand``, ``_memory_expand``, and ``_keyword_search`` (mockable
seams); ``_fuse_and_rank`` is pure and unit-testable without a DB.
"""

import math
import re

from core.nodes.base import Node
from core.task import TaskContext
from database.brain_document import BrainDocument
from database.brain_edge import BrainEdge
from database.content_chunk import ContentChunk
from memory.memory_loader_node import MemoryLoaderNode
from memory.seams import DbSeamMixin
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
        # Enables the structural neighborhood-expansion stage (Stage 1b):
        # brain_edges traversal from the top semantic hits. No-op for
        # corpora that don't declare this (e.g. "content").
        "supports_structural": True,
    },
}

# Number of top Stage-1 semantic hits whose related:-neighborhood is walked
# by the structural expansion stage (_structural_expand).
_STRUCTURAL_SEED_COUNT: int = 5

# Max number of hits returned by the independent keyword-candidate expansion
# stage (_keyword_expand), ordered by ts_rank descending.
_KEYWORD_CANDIDATE_LIMIT: int = 15

# Keyword fusion weights (tune against the Block H smoke queries):
# - _KW_WEIGHT scales the graded FTS ts_rank contribution (ts_rank values are
#   small, typically < 0.1, so this is larger than the legacy flat boost).
# - _KW_BOOST is the legacy flat boost for the ILIKE-set ("content") corpus,
#   preserved unchanged at 1.0 so that path is regression-free.
_KW_WEIGHT: float = 5.0
_KW_BOOST: float = 1.0

# Diversity cap: max chunks from the same file_path allowed in the final
# top-K, unless there aren't enough distinct-file candidates to fill the
# remaining slots (see _apply_diversity_cap).
_MAX_PER_FILE: int = 2

# Max number of SemanticMemory facts pulled in by the memory-expansion stage
# (_memory_expand). file_path=None candidates are never diversity-capped
# (_apply_diversity_cap), so this bounds the supply directly.
_MEMORY_CANDIDATE_LIMIT: int = 3


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


def _row_to_candidate(row, distance: float, config: dict, via: str = "semantic") -> dict:
    """Convert one ORM row + its cosine distance into a normalized candidate dict.

    ``via`` is a provenance tag ("semantic" or "structural") carried through
    ``_fuse_and_rank`` into the final result dicts for explainability.
    """
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
        "via": via,
    }


class RetrieveChunksNode(Node, DbSeamMixin):
    """Two-stage hybrid retrieval node (plus two optional widening stages).

    ``_session_scope`` comes from ``DbSeamMixin`` (``app/memory/seams.py``) —
    the shared seam that replaces this node's former 5 inline
    ``contextmanager(db_session)()`` call sites. See that module's docstring
    for why a mixin (not composition) preserves the per-instance test
    monkeypatches.

    Stage 1: semantic candidate set via pgvector cosine distance (top-20).
    Stage 1b: structural expansion via the related:-neighborhood of the top
        Stage-1 hits (brain corpus only; _structural_expand).
    Stage 1c: keyword-candidate expansion — an independent top-K full-text
        query (ts_rank order) unioned into the candidate set, so a document
        with a strong keyword match but a weak cosine-distance rank still
        reaches Stage 2 (brain corpus only; _keyword_expand).
    Stage 1d: memory expansion — accumulated SemanticMemory facts scoped to
        workspace_id/peer_id, opt-in via include_memory (_memory_expand).
    Stage 2: keyword re-rank via ILIKE/ts_rank scoped to the candidate IDs.
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
        expand_structural = getattr(event, "expand_structural", True)
        workspace_id = getattr(event, "workspace_id", None)
        peer_id = getattr(event, "peer_id", None)
        include_memory = getattr(event, "include_memory", False)
        chunks = self.retrieve(
            query,
            corpus=corpus,
            k=5,
            filters=filters,
            include_archived=include_archived,
            expand_structural=expand_structural,
            workspace_id=workspace_id,
            peer_id=peer_id,
            include_memory=include_memory,
        )
        task_context.update_node(
            node_name=self.node_name,
            result={"chunks": chunks},
        )
        return task_context

    def retrieve(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        query: str,
        corpus: str = "content",
        k: int = 5,
        threshold: float = 0.0,
        *,
        filters: dict | None = None,
        include_archived: bool = False,
        expand_structural: bool = True,
        workspace_id: str | None = None,
        peer_id: str | None = None,
        include_memory: bool = False,
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
            expand_structural: When True (default) and the corpus supports it
                (currently "brain" only), widens the Stage-1 semantic candidate
                set through the ``related:``-neighborhood of the top hits
                before keyword re-rank. No-op for "content" or when False.
            workspace_id: D47 workspace name to scope memory retrieval to.
                Memory expansion (Stage 1d) is a no-op unless this is not
                ``None`` **and** ``include_memory=True``.
            peer_id: Optional narrowing of memory retrieval to one entity.
            include_memory: Opt-in gate for Stage 1d memory expansion —
                surfaces accumulated ``SemanticMemory`` facts as ``via="memory"``
                candidates. Requires a non-None ``workspace_id`` to take effect.

        Returns:
            List of up to ``k`` normalized chunk dicts, each containing
            ``{"content", "section_title", "score", "source", "file_path",
            "doc_id", "title", "via"}``, sorted by fused score descending.
        """
        vector = EmbeddingService().embed_text(query)
        candidates = self._semantic_search(
            vector, corpus, limit=20, filters=filters, include_archived=include_archived
        )
        if expand_structural:
            structural = self._structural_expand(
                candidates,
                corpus,
                vector,
                filters=filters,
                include_archived=include_archived,
            )
            candidates = self._merge_candidates(candidates, structural)
        existing_ids = {c["id"] for c in candidates}
        keyword_candidates = self._keyword_expand(
            query,
            corpus,
            vector,
            existing_ids,
            filters=filters,
            include_archived=include_archived,
        )
        candidates = self._merge_candidates(candidates, keyword_candidates)
        if include_memory:
            memory_candidates = self._memory_expand(
                vector, workspace_id=workspace_id, peer_id=peer_id
            )
            candidates = self._merge_candidates(candidates, memory_candidates)
        memory_ids = {c["id"] for c in candidates if c.get("via") == "memory"}
        candidate_ids = [c["id"] for c in candidates if c["id"] not in memory_ids]
        keyword_matches = self._keyword_search(query, candidate_ids, corpus)
        return self._fuse_and_rank(candidates, keyword_matches, k, threshold)

    @staticmethod
    def _merge_candidates(candidates: list[dict], extra: list[dict]) -> list[dict]:
        """Union an extra candidate set into ``candidates``, deduped by id.

        An extra candidate whose id already appears in ``candidates`` is
        dropped (the existing candidate wins) rather than duplicated. Used for
        both the structural-expansion merge (Stage 1b) and the
        keyword-candidate-expansion merge (Stage 1c).
        """
        if not extra:
            return candidates
        existing_ids = {c["id"] for c in candidates}
        return candidates + [c for c in extra if c["id"] not in existing_ids]

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
        with self._session_scope() as session:
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

    def _structural_expand(
        self,
        candidates: list[dict],
        corpus: str,
        vector: list[float],
        *,
        filters: dict | None = None,
        include_archived: bool = False,
    ) -> list[dict]:
        """Stage 1b: widen the candidate set through the related:-neighborhood.

        Takes the top ``_STRUCTURAL_SEED_COUNT`` Stage-1 semantic candidates
        (``candidates`` is already ordered by ascending distance from
        ``_semantic_search``), looks up their ``brain_edges`` neighbors
        (matched on ``source_doc_id``), and fetches those neighbor chunks from
        ``brain_documents`` (joined by ``doc_id``, respecting the existing
        archived/status filter and any metadata ``filters``). Each neighbor is
        embed-distanced against the query ``vector`` and returned as a
        normalized candidate dict flagged ``via="structural"`` — the same
        shape ``_row_to_candidate`` produces, so ``_fuse_and_rank`` stays pure
        and untouched in its scoring contract.

        No-op (returns ``[]``, no DB touched) when the corpus doesn't declare
        ``supports_structural`` or when there are no seed doc ids / no
        resolved neighbors.

        This method is isolated so tests can patch it without a live DB.
        """
        config = _CORPUS_CONFIG[corpus]
        if not config.get("supports_structural"):
            return []

        seed_doc_ids = [
            c["doc_id"] for c in candidates[:_STRUCTURAL_SEED_COUNT] if c.get("doc_id")
        ]
        if not seed_doc_ids:
            return []

        existing_doc_ids = {c.get("doc_id") for c in candidates}

        with self._session_scope() as session:
            neighbor_doc_ids = self._resolve_neighbor_doc_ids(
                session, seed_doc_ids, existing_doc_ids
            )
            if not neighbor_doc_ids:
                return []
            return self._fetch_neighbor_candidates(
                session,
                config,
                vector,
                neighbor_doc_ids,
                filters=filters,
                include_archived=include_archived,
            )

    @staticmethod
    def _resolve_neighbor_doc_ids(session, seed_doc_ids: list, existing_doc_ids: set) -> set:
        """Query brain_edges for resolved (non-dangling) neighbors of the seed
        doc ids, excluding any doc_id already present in the candidate set."""
        edge_rows = (
            session.query(BrainEdge.target_doc_id)
            .filter(BrainEdge.source_doc_id.in_(seed_doc_ids))
            .filter(BrainEdge.target_doc_id.isnot(None))
            .all()
        )
        return {
            row.target_doc_id
            for row in edge_rows
            if row.target_doc_id not in existing_doc_ids
        }

    @staticmethod
    def _fetch_neighbor_candidates(
        session,
        config: dict,
        vector: list[float],
        neighbor_doc_ids: set,
        *,
        filters: dict | None,
        include_archived: bool,
    ) -> list[dict]:
        """Fetch + distance-score the resolved neighbor rows as candidate dicts."""
        model = config["model"]
        distance_expr = model.embedding.cosine_distance(vector)
        q = session.query(model, distance_expr.label("_distance")).filter(
            model.doc_id.in_(neighbor_doc_ids)
        )
        if filters and config.get("filter_fields"):
            q = _apply_metadata_filters(q, model, filters, config["filter_fields"])
        exclude = config.get("default_status_exclude")
        if exclude and not include_archived:
            status_col = getattr(model, "status", None)
            if status_col is not None:
                q = q.filter((status_col != exclude) | (status_col.is_(None)))
        rows = q.all()
        return [
            _row_to_candidate(row, distance, config, via="structural")
            for row, distance in rows
        ]

    @staticmethod
    def _exclude_archived_status(q, model, config: dict, include_archived: bool):
        """Filter out rows whose ``status`` equals the corpus'
        ``default_status_exclude`` (e.g. "archived"), unless the caller opts in
        via ``include_archived``. A NULL status is always kept. Shared by the
        candidate-fetching stages so the exclusion stays byte-for-byte identical.
        """
        exclude = config.get("default_status_exclude")
        if exclude and not include_archived:
            status_col = getattr(model, "status", None)
            if status_col is not None:
                q = q.filter((status_col != exclude) | (status_col.is_(None)))
        return q

    def _keyword_expand(  # pylint: disable=too-many-arguments
        self,
        query: str,
        corpus: str,
        vector: list[float],
        existing_ids: set,
        *,
        filters: dict | None = None,
        include_archived: bool = False,
    ) -> list[dict]:
        """Stage 1c: widen the candidate set through an independent keyword query.

        Runs a top-``_KEYWORD_CANDIDATE_LIMIT`` full-text query (``ts_rank``
        descending) over the corpus, gated on the corpus declaring a
        ``tsv_field`` — a no-op (returns ``[]``, no DB touched) for corpora
        without one (e.g. "content"), mirroring how ``supports_structural``
        gates ``_structural_expand``.

        Applies the same filters/include_archived/archived-status exclusion as
        ``_semantic_search``, excludes ids already present in ``existing_ids``,
        and scores each hit's cosine distance against ``vector`` the same way
        ``_fetch_neighbor_candidates`` does for structural neighbors — so the
        returned candidate dicts fit the existing ``_fuse_and_rank`` scoring
        contract unchanged. Each candidate is flagged ``via="keyword"``.

        The FTS ``@@`` match predicate already requires a genuine term match
        before a row is even ranked, so no additional minimum-rank threshold
        is applied here.

        This method is isolated so tests can patch it without a live DB.
        """
        config = _CORPUS_CONFIG[corpus]
        if not config.get("tsv_field"):
            return []

        model = config["model"]
        tsv_col = getattr(model, config["tsv_field"])
        tsquery = func.plainto_tsquery("english", query)

        with self._session_scope() as session:
            q = session.query(
                model, model.embedding.cosine_distance(vector).label("_distance")
            ).filter(tsv_col.op("@@")(tsquery))
            if existing_ids:
                q = q.filter(model.id.notin_(existing_ids))
            if filters and config.get("filter_fields"):
                q = _apply_metadata_filters(q, model, filters, config["filter_fields"])
            q = self._exclude_archived_status(q, model, config, include_archived)
            rows = (
                q.order_by(func.ts_rank(tsv_col, tsquery).desc())
                .limit(_KEYWORD_CANDIDATE_LIMIT)
                .all()
            )
            return [
                _row_to_candidate(row, distance, config, via="keyword")
                for row, distance in rows
            ]

    @staticmethod
    def _memory_expand(
        vector: list[float],
        *,
        workspace_id: str | None,
        peer_id: str | None,
    ) -> list[dict]:
        """Stage 1d: widen the candidate set through accumulated memory facts.

        No-op (returns ``[]``, no DB touched) when ``workspace_id`` is
        ``None`` — the caller (``retrieve()``) already gates on
        ``include_memory``, so this method only additionally enforces the
        non-None ``workspace_id`` half of design decision 2.

        Calls ``MemoryLoaderNode.retrieve()`` in **cosine mode**, reusing the
        Stage-1 query embedding (``vector``) rather than re-embedding the
        question text — cosine mode sets ``use_decay_weighting=False``
        internally, so decay is applied here in the adapter instead, by
        multiplying the raw cosine score by the ``effective_confidence``
        already computed by ``_score_fact``.

        Adapts each fact dict to the standard candidate-dict shape consumed
        by ``_fuse_and_rank``. The ``distance`` inversion is deliberate:
        ``_fuse_and_rank`` computes ``similarity = 1.0 - distance``, so
        storing ``distance = 1.0 - (score * effective_confidence)`` round-trips
        back to the decayed score with ``_fuse_and_rank`` left unchanged.
        Each candidate is flagged ``via="memory"`` and carries
        ``file_path=None``/``doc_id=None``/``title=None`` (memory facts have
        no source-file provenance).

        This method is isolated so tests can patch it without a live DB.
        """
        if workspace_id is None:
            return []

        result = MemoryLoaderNode().retrieve(
            workspace_id=workspace_id,
            peer_id=peer_id,
            query_embedding=vector,
            top_k=_MEMORY_CANDIDATE_LIMIT,
        )
        return [
            {
                "id": fact["id"],
                "content": fact["fact"],
                "section_title": None,
                "is_section_title": False,
                "distance": 1.0 - (fact["score"] * fact["effective_confidence"]),
                "file_path": None,
                "doc_id": None,
                "title": None,
                "via": "memory",
            }
            for fact in result["facts"]
        ]

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

    def _keyword_search_fts(
        self, query: str, candidate_ids: list, config: dict, tsv_field: str
    ) -> dict:
        """Graded full-text search: returns ``dict[id -> ts_rank]`` (FTS corpora)."""
        model = config["model"]
        tsv_col = getattr(model, tsv_field)
        tsquery = func.plainto_tsquery("english", query)
        rank = func.ts_rank(tsv_col, tsquery)
        with self._session_scope() as session:
            q = (
                session.query(model.id, rank.label("kw_rank"))
                .filter(model.id.in_(candidate_ids))
                .filter(tsv_col.op("@@")(tsquery))
            )
            return {row.id: float(row.kw_rank) for row in q.all()}

    def _keyword_search_ilike(self, query: str, candidate_ids: list, config: dict) -> set:
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

        with self._session_scope() as session:
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
            "source", "file_path", "doc_id", "title", "via"}`` sorted by score
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
                    # Provenance flag: "semantic" (Stage 1) or "structural"
                    # (Stage 1b, related:-neighborhood expansion).
                    "via": c.get("via", "semantic"),
                }
            )

        scored.sort(key=lambda c: c["score"], reverse=True)
        return self._apply_diversity_cap(scored, k)

    @staticmethod
    def _apply_diversity_cap(scored: list[dict], k: int) -> list[dict]:
        """Cap results-per-``file_path`` in the final top-``k`` selection.

        Walks ``scored`` (already sorted by score descending) and greedily
        selects up to ``k`` results, allowing at most ``_MAX_PER_FILE`` from
        any single ``file_path``. A candidate whose file has hit the cap is
        skipped on the first pass so a genuinely complementary result from a
        different file gets the freed slot. If the first pass can't fill all
        ``k`` slots (not enough distinct-file candidates), a second pass backfills
        the remaining slots from the skipped, over-cap candidates in score order
        — so the cap only reorders/displaces results when there is something to
        replace them with, never drops results outright.

        A ``file_path`` of ``None`` (corpora without citation metadata, e.g.
        "content" chunks with no source file) is never capped — each is treated
        as its own singleton group.
        """
        counts: dict = {}
        selected: list[dict] = []
        overflow: list[dict] = []
        for c in scored:
            file_path = c.get("file_path")
            if file_path is None:
                selected.append(c)
                if len(selected) >= k:
                    break
                continue
            if counts.get(file_path, 0) < _MAX_PER_FILE:
                counts[file_path] = counts.get(file_path, 0) + 1
                selected.append(c)
                if len(selected) >= k:
                    break
            else:
                overflow.append(c)

        if len(selected) < k and overflow:
            selected.extend(overflow[: k - len(selected)])

        return selected[:k]
