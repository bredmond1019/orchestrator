"""app/brain/retrieval_engine.py — the promoted two-stage hybrid retrieval core.

Promoted out of ``app/workflows/document_qa_workflow_nodes/retrieve_chunks_node.py``
(OR.K2 task 1, CLAUDE.md standing rule 10 — extract on the second consumer):
``RetrieveChunksNode`` (the ``DOCUMENT_QA`` workflow) and ``app/brain/retrieval.py``
(``syn recall --hybrid`` / ``GET /recall?hybrid=true`` / the manual
``scripts/query_brain.py --hybrid`` smoke test) both need the identical
semantic -> structural -> keyword -> memory -> fuse-and-rank pipeline. Before
this promotion, ``app/brain/retrieval.py::hybrid_search`` reached into the
workflow node with a function-local import — an inverted dependency (a
"brain" read core depending on a "workflow" node) that also silently dropped
every argument except ``query``/``limit`` (no workspace/filters scoping on
the hybrid path). ``app/brain/`` must import ``app/workflows/`` nowhere; this
module is why that grep now holds.

This is not a pure refactor: every DB-hitting stage now accepts an optional
``session`` (a caller-supplied SQLAlchemy session, or a session-factory
callable taking no arguments) so a caller — ``recall()``, an eval harness,
future ``OR.K1`` query-log wiring — can thread one session through the whole
pipeline instead of each stage opening (and closing) its own. When ``session``
is ``None`` (the default), behavior is byte-identical to before the
promotion: each DB-touching stage opens its own short-lived session via
``_session_scope()``.

Mechanics carried over verbatim from the node: 7 of the former instance
methods were already ``@staticmethod`` (no ``self`` use at all); the other 5
touched only ``self._session_scope()``. All 12 are module-level functions
here. Ranking math (``_fuse_and_rank``, ``_apply_diversity_cap``) is untouched
byte-for-byte so unscoped-query rankings stay identical pre/post promotion.
"""

import math
import re
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime

from database.brain_document import BrainDocument
from database.brain_edge import BrainEdge
from database.content_chunk import ContentChunk
from database.session import db_session
from memory.decay import effective_confidence, weeks_between
from memory.memory_loader_node import MemoryLoaderNode
from services.embedding_service import EmbeddingService
from sqlalchemy import func, or_

from brain.query_log import log_retrieval

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
# - _KW_WEIGHT scales the graded FTS ts_rank contribution. Both ts_rank and
#   the semantic similarity term it is fused against are bounded in [0, 1],
#   but ts_rank is typically small (< 0.1) while a 5.0 multiplier let it
#   swing the fused score by up to 0.5 — enough for a keyword match on a
#   generic word to outrank every semantic hit on keyword-dense queries
#   (measured in planning/artifacts/rag-diagnosis-2026-08-07.md). 0.5 keeps
#   the two terms on comparable scale: a strong ts_rank can still nudge the
#   ranking without being able to override semantic relevance outright.
# - _KW_BOOST is the legacy flat boost for the ILIKE-set ("content") corpus,
#   preserved unchanged at 1.0 so that path is regression-free.
_KW_WEIGHT: float = 0.5
_KW_BOOST: float = 1.0

# Diversity cap: max chunks from the same file_path allowed in the final
# top-K, unless there aren't enough distinct-file candidates to fill the
# remaining slots (see _apply_diversity_cap).
_MAX_PER_FILE: int = 2

# Max number of SemanticMemory facts pulled in by the memory-expansion stage
# (_memory_expand). file_path=None candidates are never diversity-capped
# (_apply_diversity_cap), so this bounds the supply directly.
_MEMORY_CANDIDATE_LIMIT: int = 3

# Per-week decay factor applied to "brain" corpus results by authored_at age
# (_fuse_and_rank), gated by DocumentQAEventSchema.apply_decay (default True).
# Deliberately far gentler than memory's 0.95/week (design decision 4): at
# 0.95/wk a 6-month-old doc retains ~26%, burying the decisions log; at
# 0.99/wk it retains ~77%. Rows with authored_at=None are never decayed.
_DOC_DECAY_FACTOR: float = 0.99

# Multiplier applied to a candidate's semantic similarity when the chunk is a
# header-only "section title" chunk (`is_section_title`, set at ingest by
# `brain.ingest._is_header_only_chunk`). Ported from rag-engine-rs's
# `two_stage_retrieval.rs` at 2.0 and never measured until
# `OR.ticket.section-title-boost`, which found it a real ranking defect: at 2.0,
# 11 of the 23 golden-set queries returned a header stub ("## Decision",
# "## Amendment Log") at rank 1 and answers were grounded against near-empty
# headers. Sweeping the weight on the live corpus: 2.0 -> 1.0 gives MRR +0.0877,
# groundedness +0.0637, groundedness_on_hits +0.0774, recall@5 +0.0588, with
# recall@10 and abstain_correctness unchanged; rank-1 stubs 11/23 -> 0/23 and
# median rank-1 chunk length 527 -> 1105 chars.
#
# Why exactly 1.0 and not a sub-1.0 penalty: 0.9, 0.75, 0.5 and 0.0 all score
# byte-identically to 1.0 — a flat plateau, because once a stub stops
# out-ranking body chunks, pushing it lower only reorders results that never
# reach the top-k. 1.0 is the most conservative point on the optimal plateau; a
# penalty would be unmeasurable over-fitting to 23 cases. The flag itself is
# still written, stored, and surfaced in results — only its ranking effect is
# neutral, so a future block can still use the signal.
_SECTION_TITLE_WEIGHT: float = 1.0

# Number of top-ranked chunk scores averaged by compute_retrieval_confidence.
# The single top score alone can never fall below sigmoid(0) = 0.5 once any
# match is found, and an out-of-domain query can still produce one spuriously
# strong hit while the rest of the result set is weak (measured:
# neg-02-jupiter-moons top-1 0.7684 vs mean-of-top-5 0.4800) -- the window
# mean discriminates real corpus coverage where the single top score cannot.
_CONFIDENCE_WINDOW: int = 5


def _session_scope(session=None):
    """Return a context manager yielding a SQLAlchemy session.

    When ``session`` is ``None`` (the default), opens a new short-lived
    session via ``contextmanager(db_session)()`` — byte-identical to the
    pre-promotion per-stage behavior. When a session (or a zero-arg
    session-factory callable) is supplied, it is reused as-is via
    ``nullcontext`` so a caller can thread one session through the whole
    pipeline without each stage opening its own.

    Isolated so tests can monkeypatch ``retrieval_engine.db_session`` (the
    module-level import) to yield a real (e.g. in-memory SQLite) session
    without touching the deployment database.
    """
    if session is not None:
        return nullcontext(session() if callable(session) else session)
    return contextmanager(db_session)()


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

    ``via`` is a provenance tag ("semantic", "structural", "keyword", ...)
    carried through ``_fuse_and_rank`` into the final result dicts for
    explainability.
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
        "authored_at": getattr(row, "authored_at", None),
        "via": via,
    }


def compute_retrieval_confidence(chunks: list[dict]) -> float:
    """Squash the top-window mean fused retrieval score into a [0, 1] signal.

    Uses a logistic squash (``1 / (1 + e^-mean)``) on the mean of the
    ``_CONFIDENCE_WINDOW`` highest-scoring chunks' fused ``score`` — monotonic
    in that mean by construction, so a stronger window mean always yields a
    higher (or equal) confidence. Chosen over a bare top-1 score because an
    out-of-domain query can still produce one spuriously strong hit while the
    rest of its retrieved set is weak; the single top score can never fall
    below sigmoid(0) = 0.5 once any match exists, so it cannot discriminate
    those cases (measured: neg-02-jupiter-moons top-1 0.7684 vs
    mean-of-top-5 0.4800). Chunks are assumed pre-sorted by descending score
    (the pipeline's normal output order); only the first ``_CONFIDENCE_WINDOW``
    entries are used, so a low-scoring 6th-plus chunk never moves the result.

    Returns 0.0 when ``chunks`` is empty (no retrieval signal at all) —
    the design decision 2 "zero chunks" abstain trigger downstream.
    """
    if not chunks:
        return 0.0
    window = chunks[:_CONFIDENCE_WINDOW]
    mean_score = sum(c["score"] for c in window) / len(window)
    return 1.0 / (1.0 + math.exp(-mean_score))


def retrieve(  # pylint: disable=too-many-arguments,too-many-locals
    query: str,
    *,
    corpus: str = "content",
    k: int = 5,
    threshold: float = 0.0,
    filters: dict | None = None,
    include_archived: bool = False,
    expand_structural: bool = True,
    workspace_id: str | None = None,
    peer_id: str | None = None,
    include_memory: bool = False,
    apply_decay: bool = True,
    session=None,
    embedder=None,
    surface: str | None = None,
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
        apply_decay: When True (default), "brain" corpus candidates with a
            non-None ``authored_at`` are down-weighted by age in
            ``_fuse_and_rank`` (see ``_DOC_DECAY_FACTOR``). Set False to
            reproduce pre-decay ranking exactly.
        session: Optional SQLAlchemy session (or zero-arg session-factory)
            threaded through every DB-touching stage. ``None`` (the default)
            preserves today's per-stage session-opening behavior, so ranking
            and existing snapshots stay byte-identical.
        embedder: Optional object exposing ``embed_text(query) -> list[float]``
            (e.g. an ``EmbeddingService`` instance). ``None`` constructs a
            fresh ``EmbeddingService()`` as before.
        surface: Optional calling-surface tag (``"cli"`` / ``"http"`` /
            ``"workflow"`` / ``"mcp"``) threaded through to the OR.K1 query
            log (``app/brain/query_log.py``). ``None`` (the default) is
            logged as ``"unknown"``; has no effect on retrieval behavior.

    Returns:
        List of up to ``k`` normalized chunk dicts, each containing
        ``{"content", "section_title", "is_section_title", "score", "source",
        "file_path", "doc_id", "title", "via"}``, sorted by fused score
        descending. ``is_section_title`` is informational only — it no longer
        weights the score (see ``_SECTION_TITLE_WEIGHT``).
    """
    start = time.monotonic()
    embedder = embedder if embedder is not None else EmbeddingService()
    vector = embedder.embed_text(query)
    candidates = _semantic_search(
        vector,
        corpus,
        limit=20,
        filters=filters,
        include_archived=include_archived,
        session=session,
    )
    if expand_structural:
        structural = _structural_expand(
            candidates,
            corpus,
            vector,
            filters=filters,
            include_archived=include_archived,
            session=session,
        )
        candidates = _merge_candidates(candidates, structural)
    existing_ids = {c["id"] for c in candidates}
    keyword_candidates = _keyword_expand(
        query,
        corpus,
        vector,
        existing_ids,
        filters=filters,
        include_archived=include_archived,
        session=session,
    )
    candidates = _merge_candidates(candidates, keyword_candidates)
    if include_memory:
        memory_candidates = _memory_expand(vector, workspace_id=workspace_id, peer_id=peer_id)
        candidates = _merge_candidates(candidates, memory_candidates)
    memory_ids = {c["id"] for c in candidates if c.get("via") == "memory"}
    candidate_ids = [c["id"] for c in candidates if c["id"] not in memory_ids]
    keyword_matches = _keyword_search(query, candidate_ids, corpus, session=session)
    results = _fuse_and_rank(candidates, keyword_matches, k, threshold, apply_decay=apply_decay)
    log_retrieval(
        query,
        results,
        surface=surface,
        workspace_id=workspace_id,
        hybrid=True,
        retrieval_confidence=compute_retrieval_confidence(results),
        latency_ms=int((time.monotonic() - start) * 1000),
    )
    return results


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
    vector: list[float],
    corpus: str,
    limit: int,
    filters: dict | None = None,
    include_archived: bool = False,
    session=None,
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

    This function is isolated so tests can patch it without a live DB.
    """
    config = _CORPUS_CONFIG[corpus]
    model = config["model"]
    with _session_scope(session) as db:
        distance_expr = model.embedding.cosine_distance(vector)
        q = db.query(model, distance_expr.label("_distance"))
        if filters and config.get("filter_fields"):
            q = _apply_metadata_filters(q, model, filters, config["filter_fields"])
        # Default: exclude archived docs unless the caller opts in. A NULL
        # status is kept (only an explicit "archived" is filtered).
        q = _exclude_archived_status(q, model, config, include_archived)
        rows = q.order_by(distance_expr).limit(limit).all()
        return [_row_to_candidate(row, distance, config) for row, distance in rows]


def _structural_expand(
    candidates: list[dict],
    corpus: str,
    vector: list[float],
    *,
    filters: dict | None = None,
    include_archived: bool = False,
    session=None,
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

    This function is isolated so tests can patch it without a live DB.
    """
    config = _CORPUS_CONFIG[corpus]
    if not config.get("supports_structural"):
        return []

    seed_doc_ids = [c["doc_id"] for c in candidates[:_STRUCTURAL_SEED_COUNT] if c.get("doc_id")]
    if not seed_doc_ids:
        return []

    existing_doc_ids = {c.get("doc_id") for c in candidates}

    with _session_scope(session) as db:
        neighbor_doc_ids = _resolve_neighbor_doc_ids(db, seed_doc_ids, existing_doc_ids)
        if not neighbor_doc_ids:
            return []
        return _fetch_neighbor_candidates(
            db,
            config,
            vector,
            neighbor_doc_ids,
            filters=filters,
            include_archived=include_archived,
        )


def _resolve_neighbor_doc_ids(session, seed_doc_ids: list, existing_doc_ids: set) -> set:
    """Query brain_edges for resolved (non-dangling) neighbors of the seed
    doc ids, excluding any doc_id already present in the candidate set."""
    edge_rows = (
        session.query(BrainEdge.target_doc_id)
        .filter(BrainEdge.source_doc_id.in_(seed_doc_ids))
        .filter(BrainEdge.target_doc_id.isnot(None))
        .all()
    )
    return {row.target_doc_id for row in edge_rows if row.target_doc_id not in existing_doc_ids}


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
    q = _exclude_archived_status(q, model, config, include_archived)
    rows = q.all()
    return [_row_to_candidate(row, distance, config, via="structural") for row, distance in rows]


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
    query: str,
    corpus: str,
    vector: list[float],
    existing_ids: set,
    *,
    filters: dict | None = None,
    include_archived: bool = False,
    session=None,
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

    This function is isolated so tests can patch it without a live DB.
    """
    config = _CORPUS_CONFIG[corpus]
    if not config.get("tsv_field"):
        return []

    model = config["model"]
    tsv_col = getattr(model, config["tsv_field"])
    tsquery = func.plainto_tsquery("english", query)

    with _session_scope(session) as db:
        q = db.query(model, model.embedding.cosine_distance(vector).label("_distance")).filter(
            tsv_col.op("@@")(tsquery)
        )
        if existing_ids:
            q = q.filter(model.id.notin_(existing_ids))
        if filters and config.get("filter_fields"):
            q = _apply_metadata_filters(q, model, filters, config["filter_fields"])
        q = _exclude_archived_status(q, model, config, include_archived)
        rows = (
            q.order_by(func.ts_rank(tsv_col, tsquery).desc()).limit(_KEYWORD_CANDIDATE_LIMIT).all()
        )
        return [_row_to_candidate(row, distance, config, via="keyword") for row, distance in rows]


def _memory_expand(
    vector: list[float],
    *,
    workspace_id: str | None,
    peer_id: str | None,
) -> list[dict]:
    """Stage 1d: widen the candidate set through accumulated memory facts.

    No-op (returns ``[]``, no DB touched) when ``workspace_id`` is
    ``None`` — the caller (``retrieve()``) already gates on
    ``include_memory``, so this function only additionally enforces the
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

    This function is isolated so tests can patch it without a live DB.
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
    query: str,
    candidate_ids: list,
    corpus: str,
    *,
    session=None,
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
        return _keyword_search_fts(query, candidate_ids, config, tsv_field, session=session)
    return _keyword_search_ilike(query, candidate_ids, config, session=session)


def _keyword_search_fts(
    query: str, candidate_ids: list, config: dict, tsv_field: str, *, session=None
) -> dict:
    """Graded full-text search: returns ``dict[id -> ts_rank]`` (FTS corpora)."""
    model = config["model"]
    tsv_col = getattr(model, tsv_field)
    tsquery = func.plainto_tsquery("english", query)
    rank = func.ts_rank(tsv_col, tsquery)
    with _session_scope(session) as db:
        q = (
            db.query(model.id, rank.label("kw_rank"))
            .filter(model.id.in_(candidate_ids))
            .filter(tsv_col.op("@@")(tsquery))
        )
        return {row.id: float(row.kw_rank) for row in q.all()}


def _keyword_search_ilike(query: str, candidate_ids: list, config: dict, *, session=None) -> set:
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

    with _session_scope(session) as db:
        q = db.query(model.id).filter(model.id.in_(candidate_ids)).filter(or_(*ilike_filters))
        return {row.id for row in q.all()}


def _fuse_and_rank(  # pylint: disable=too-many-locals
    candidates: list[dict],
    keyword_matches: set | dict,
    k: int,
    threshold: float,
    *,
    apply_decay: bool = True,
) -> list[dict]:
    """Pure score fusion, NaN filtering, decay, and top-k selection.

    Score formula (ported from rag-engine-rs ``two_stage_retrieval.rs``):

        title_weight = _SECTION_TITLE_WEIGHT if is_section_title else 1.0
        score = (1.0 - distance) * title_weight + keyword_contribution

    ``_SECTION_TITLE_WEIGHT`` is ``1.0`` (neutral) — the Rust port's ``2.0``
    was measured as a ranking defect and retired; see the constant's comment.

    The keyword contribution depends on the shape of ``keyword_matches``:

    - ``dict[id -> ts_rank]`` (FTS corpora): graded —
      ``_KW_WEIGHT * ts_rank``. A stronger / better-weighted match scores
      higher than a weak one.
    - ``set[id]`` (legacy ILIKE corpora): flat ``_KW_BOOST`` for membership.

    When ``apply_decay`` is True (default) and a candidate carries a
    non-None ``authored_at``, the fused score is additionally multiplied
    by ``effective_confidence(1.0, _DOC_DECAY_FACTOR, weeks_elapsed)`` —
    the same pure decay helper block OR.S uses for memory facts
    (``app/memory/decay.py``), reused as-is per design decision 4. A
    candidate with ``authored_at=None`` (pre-backfill rows, or corpora
    that don't carry the field at all, e.g. "content" and memory
    candidates) is never decayed. ``apply_decay=False`` reproduces
    pre-block ranking exactly regardless of ``authored_at``.

    NaN-safe: candidates whose ``distance`` is NaN are filtered out before
    sorting (the Rust ``total_cmp`` guard, which never panics on NaN).

    Args:
        candidates: Stage-1 candidates with ``id``, ``distance``,
            ``is_section_title``, ``content``, ``section_title`` keys.
        keyword_matches: Either a ``dict[id -> ts_rank]`` (graded FTS) or a
            ``set[id]`` (legacy binary) of keyword hits.
        k: Maximum number of results to return.
        threshold: Minimum fused score to include a result.
        apply_decay: Opt-out gate for the ``authored_at`` age decay.

    Returns:
        List of normalized dicts ``{"content", "section_title",
        "is_section_title", "score", "source", "file_path", "doc_id",
        "title", "via"}`` sorted by score descending, length <= ``k``.
    """
    graded = isinstance(keyword_matches, dict)
    now = datetime.now()
    scored = []
    for c in candidates:
        distance = c["distance"]
        # NaN guard — replicate Rust total_cmp; skip NaN distances
        if math.isnan(distance):
            continue
        similarity = 1.0 - distance
        is_section_title = bool(c.get("is_section_title"))
        title_weight = _SECTION_TITLE_WEIGHT if is_section_title else 1.0
        if graded:
            keyword_boost = _KW_WEIGHT * keyword_matches.get(c["id"], 0.0)
        else:
            keyword_boost = _KW_BOOST if c["id"] in keyword_matches else 0.0
        score = similarity * title_weight + keyword_boost
        authored_at = c.get("authored_at")
        # isinstance guard (not "is not None"): a candidate dict built from
        # a loosely-specced test double (or any future source that doesn't
        # carry a real datetime) must degrade to undecayed rather than
        # raise inside weeks_between's datetime arithmetic.
        if apply_decay and isinstance(authored_at, datetime):
            score *= effective_confidence(1.0, _DOC_DECAY_FACTOR, weeks_between(authored_at, now))
        if score < threshold:
            continue
        scored.append(
            {
                "id": c["id"],
                "content": c["content"],
                "section_title": c.get("section_title"),
                # Surfaced (OR.ticket.section-title-boost) so callers — the eval
                # harness above all — can tell a header-only stub from a body
                # chunk without re-deriving it from content length.
                "is_section_title": is_section_title,
                "score": score,
                "source": c.get("section_title") or "General",
                # Provenance / citation fields (carried through from candidates).
                "file_path": c.get("file_path"),
                "doc_id": c.get("doc_id"),
                "title": c.get("title"),
                # Provenance flag: "semantic" (Stage 1), "structural" (Stage 1b),
                # "keyword" (Stage 1c), or "memory" (Stage 1d).
                "via": c.get("via", "semantic"),
            }
        )

    scored.sort(key=lambda c: c["score"], reverse=True)
    return _apply_diversity_cap(scored, k)


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
