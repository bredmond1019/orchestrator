"""app/brain/retrieval.py — the Brain's recall read core (exact-id, semantic, hybrid).

Extracted out of ``scripts/query_brain.py`` (OR.N1, CLAUDE.md rule 10 — extract
on the second consumer) once both the manual `query_brain.py` smoke-test CLI
and the new `syn recall` console command needed the same
exact-id / semantic / hybrid search paths. Behavior is byte-for-byte identical
to the original script functions; only the module changed. Display formatting
(`format_result` / `format_hybrid_result`) stays in `scripts/query_brain.py` —
it is not part of the read core.

OR.K2 task 1 fixed two defects here (this module is not the read core's pure
refactor target — it is where the workspace-scoping bug actually lived):

- Every path now actually scopes by ``workspace`` (resolved to
  ``filters={"project": workspace}`` per D47) — before this block,
  ``hybrid_search`` dropped every argument except ``query``/``limit``, and
  ``exact_id_lookup``/``semantic_search`` took no filter parameter at all, so
  ``syn recall --workspace X`` was a no-op on every retrieval path.
- ``hybrid_search`` now calls ``brain.retrieval_engine.retrieve`` directly
  instead of a function-local import of ``RetrieveChunksNode`` — the inverted
  dependency (a "brain" module importing a "workflow" node) is gone;
  ``app/brain/`` imports ``app/workflows/`` nowhere.

``recall()``'s return shape is normalized across all three paths to one dict
shape: ``{doc_id, file_path, title, section, content, score, via}``, with
``score`` always a similarity where higher is better (``1.0 - distance`` for
the exact-id/semantic paths — an exact-id hit is a perfect match, so
``score=1.0``; the hybrid path's fused score is already similarity-oriented).
"""

import re
import time

from brain import retrieval_engine
from brain.query_log import log_retrieval

# Matches structured brain identifiers like "D20", "OR.V", "MV.3B.Q": one to
# five uppercase letters, followed by either a run of digits (D20) or one or
# more dot-separated alphanumeric segments (OR.V, MV.3B.Q). Requiring digits
# or a dot segment (rather than bare letters) keeps this from matching
# ordinary capitalized words like "I" or "What".
ID_PATTERN = re.compile(r"\b[A-Z]{1,5}(?:[0-9]{1,4}|(?:\.[A-Z0-9]{1,5})+)\b")


def find_exact_id(query: str) -> str | None:
    """Return the first structured-ID token in `query`, or None if absent.

    Recognizes bare codes such as `D20`, `OR.V`, `MV.3B.Q` — identifiers that
    embeddings don't reliably encode as semantically distinct from ordinary
    prose (see planning/ticket-brain-retrieval-improvements/tasks.md Finding B).
    """
    match = ID_PATTERN.search(query)
    return match.group(0) if match else None


def _workspace_filters(workspace: str | None) -> dict | None:
    """Resolve a `workspace` name to the `{"project": workspace}` filter (D47).

    Returns `None` when `workspace` is unset so default (unscoped) behavior
    is unchanged.
    """
    return {"project": workspace} if workspace else None


def exact_id_lookup(
    id_str: str, session, limit: int = 5, *, filters: dict | None = None
) -> list:
    """Resolve `id_str` via a deterministic doc_id/file_path ILIKE lookup.

    Args:
        id_str: The structured ID token (e.g. "D20") to look up.
        session: An open SQLAlchemy session (injected by the caller).
        limit: Maximum number of rows to return.
        filters: Optional metadata WHERE clauses (e.g. `{"project": "..."}`)
            scoping the lookup, applied the same way `_semantic_search`
            applies them for the hybrid/semantic paths.

    Returns:
        A list of `BrainDocument` rows matching `id_str` in either `doc_id`
        or `file_path`, most-relevant first (doc_id exact-ish matches before
        file_path substring matches).
    """
    # local import: app/ only on sys.path at call time
    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel
    from sqlalchemy import or_  # pylint: disable=import-outside-toplevel

    pattern = f"%{id_str}%"
    query = session.query(BrainDocument).filter(
        or_(BrainDocument.doc_id.ilike(pattern), BrainDocument.file_path.ilike(pattern))
    )
    if filters:
        filter_fields = retrieval_engine._CORPUS_CONFIG["brain"]["filter_fields"]  # pylint: disable=protected-access
        query = retrieval_engine._apply_metadata_filters(  # pylint: disable=protected-access
            query, BrainDocument, filters, filter_fields
        )
    return query.limit(limit).all()


def semantic_search(
    query: str,
    session,
    embedding_service,
    limit: int = 5,
    *,
    filters: dict | None = None,
) -> list[tuple]:
    """Embed `query` and return the `limit` nearest `BrainDocument` rows.

    Args:
        query: Natural-language question to embed and search for.
        session: An open SQLAlchemy session (injected by the caller via
            `database.session.db_session` — never constructed here).
        embedding_service: An `EmbeddingService` instance (injected so tests
            can substitute a fake without a live Ollama/Voyage call).
        limit: Maximum number of rows to return.
        filters: Optional metadata WHERE clauses (e.g. `{"project": "..."}`).

    Returns:
        A list of `(BrainDocument, distance)` tuples ordered nearest-first
        (cosine distance — 0.0 is identical, larger is less similar).
    """
    # local import: app/ only on sys.path at call time
    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel

    vector = embedding_service.embed_text(query)
    distance = BrainDocument.embedding.cosine_distance(vector).label("distance")
    q = session.query(BrainDocument, distance)
    if filters:
        filter_fields = retrieval_engine._CORPUS_CONFIG["brain"]["filter_fields"]  # pylint: disable=protected-access
        q = retrieval_engine._apply_metadata_filters(  # pylint: disable=protected-access
            q, BrainDocument, filters, filter_fields
        )
    return q.order_by(distance).limit(limit).all()


def _semantic_search_corpus(
    query: str,
    session,
    embedding_service,
    corpus: str,
    limit: int = 5,
    *,
    filters: dict | None = None,
) -> list[dict]:
    """Non-hybrid semantic search scoped to a non-``"brain"`` corpus.

    ``semantic_search()`` above queries `BrainDocument` unconditionally, so
    it cannot serve `corpus="code"`/`corpus="content"` — that was the
    corpus-exclusivity bug (finding #13,
    `SY.ticket.recall-corpus-exclusivity`). This reuses
    `retrieval_engine._semantic_search`, the same `_CORPUS_CONFIG`-scoped
    Stage-1 query the `hybrid` path already threads `corpus` through, so a
    `--corpus code` request without `--hybrid` actually queries
    `code_chunks` instead of silently falling back to brain/content rows.

    Args:
        query: Natural-language question to embed and search for.
        session: An open SQLAlchemy session.
        embedding_service: An `EmbeddingService` instance.
        corpus: The corpus to query — any key in
            `retrieval_engine._CORPUS_CONFIG` other than `"brain"` (the
            caller routes `"brain"` through `semantic_search()` instead).
        limit: Maximum number of results to return.
        filters: Optional metadata WHERE clauses scoped to `corpus`'s own
            `filter_fields` (e.g. `{"repo": ...}` for `"code"`).

    Returns:
        A list of normalized result dicts in `recall()`'s standard shape
        (`_normalize_engine_chunk`'s output), corpus-exclusive by
        construction — `_semantic_search` only ever queries `corpus`'s own
        table.
    """
    vector = embedding_service.embed_text(query)
    candidates = retrieval_engine._semantic_search(  # pylint: disable=protected-access
        vector, corpus, limit, filters=filters, session=session
    )
    normalized = []
    for candidate in candidates:
        chunk = dict(candidate)
        chunk["score"] = 1.0 - chunk.pop("distance")
        normalized.append(_normalize_engine_chunk(chunk, corpus=corpus))
    return normalized


def _normalize_engine_chunk(chunk: dict, *, corpus: str = "brain") -> dict:
    """Normalize a `retrieval_engine.retrieve()` chunk dict into `recall()`'s shape.

    The "code" corpus has no `doc_id`/`title` columns on `CodeChunk` (those
    are `BrainDocument`-only), so both are derived here rather than added as
    new fields — the normalized dict's key set must stay identical across
    every corpus (OR.3.B's contract pin on `RecallResponse`/`RecallResult`).
    `title` is recovered from the pre-rendered `section` citation string
    (`"<symbol_name> (<symbol_kind>, L<start>-<end>)"` or
    `"<file basename> (file, L1-N)"` for the whole-file fallback — see
    `app.brain.code_chunking`), and `doc_id` is a stable synthetic id built
    from the chunk's own row id.
    """
    doc_id = chunk.get("doc_id")
    title = chunk.get("title")
    if corpus == "code" and doc_id is None:
        doc_id = f"code:{chunk.get('id')}"
        section_title = chunk.get("section_title") or ""
        title = section_title.split(" (", 1)[0] or None
    return {
        "doc_id": doc_id,
        "file_path": chunk.get("file_path"),
        "title": title,
        "section": chunk.get("section_title"),
        "content": chunk.get("content"),
        "score": chunk.get("score"),
        "via": chunk.get("via", "semantic"),
    }


def hybrid_search(
    query: str,
    limit: int = 5,
    *,
    filters: dict | None = None,
    workspace: str | None = None,
    session=None,
    surface: str | None = None,
    corpus: str = "brain",
) -> list[dict]:
    """Run the promoted `retrieval_engine.retrieve` fusion pipeline over the brain corpus.

    Reuses the production `retrieval_engine.retrieve` pipeline (semantic ->
    structural -> keyword expansion -> fuse-and-rank) instead of the raw
    cosine-distance-only `semantic_search` above, so a manual test session
    sees the same ranking the production `DOCUMENT_QA` workflow would
    produce. `app/brain/` imports `app/workflows/` nowhere — this used to
    reach into `RetrieveChunksNode` via a function-local import; that
    inverted dependency is gone.

    Args:
        query: Natural-language question to search for.
        limit: Maximum number of fused results to return (`k`).
        filters: Optional metadata WHERE clauses, merged with the resolved
            `workspace` filter (an explicit `filters["project"]` wins if both
            are supplied and disagree — `workspace` is the common case).
        workspace: D47 workspace name; resolves to `filters={"project": ...}`.
        session: Optional SQLAlchemy session threaded through every stage.
        surface: Optional calling-surface tag threaded through to
            `retrieval_engine.retrieve` for the OR.K1 query log; `retrieve()`
            is the single logging choke point for this path, so no separate
            log write happens here.
        corpus: Corpus to query — `"brain"` (default), `"content"`, or
            `"code"` (OR.P). Threaded straight into `retrieval_engine.retrieve`.

    Returns:
        A list of up to `limit` normalized result dicts (the same
        `{doc_id, file_path, title, section, content, score, via}` shape
        `recall()` returns on every path), sorted by score descending.
    """
    resolved_filters = {
        **(_workspace_filters(workspace) or {}),
        **(filters or {}),
    } or None
    chunks = retrieval_engine.retrieve(
        query,
        corpus=corpus,
        k=limit,
        filters=resolved_filters,
        workspace_id=workspace,
        session=session,
        surface=surface,
    )
    return [_normalize_engine_chunk(c, corpus=corpus) for c in chunks]


def _normalize_doc_row(doc, score: float, *, via: str) -> dict:
    """Normalize a `BrainDocument` row + its similarity score into a plain dict."""
    return {
        "doc_id": getattr(doc, "doc_id", None),
        "file_path": doc.file_path,
        "title": doc.title,
        "section": doc.section,
        "content": doc.content,
        "score": score,
        "via": via,
    }


def _log_recall(  # pylint: disable=too-many-arguments
    query: str,
    results: list[dict],
    *,
    workspace: str | None,
    surface: str | None,
    start: float,
    limit: int | None = None,
    filters: dict | None = None,
    embedding_model: str | None = None,
    corpus: str = "brain",
) -> None:
    """Shared OR.K1 logging call for `recall()`'s exact-id/semantic paths.

    The hybrid path is logged once, inside `retrieval_engine.retrieve()`
    (the single choke point) — this covers the other half: the two paths
    that never call `retrieve()`.

    Covers three non-hybrid dispatch branches: `exact_id_lookup` and
    `semantic_search` (both `"brain"`-only — exact-id lookup is a
    brain-corpus concept and `semantic_search` hardcodes `BrainDocument`),
    and `_semantic_search_corpus` (any other corpus, scoped via
    `retrieval_engine._CORPUS_CONFIG`). The `corpus` tag passed through here
    always matches the table the results actually came from as of the
    `SY.ticket.recall-corpus-exclusivity` fix.
    """
    log_retrieval(
        query,
        results,
        surface=surface,
        workspace_id=workspace,
        hybrid=False,
        retrieval_confidence=retrieval_engine.compute_retrieval_confidence(results),
        latency_ms=int((time.monotonic() - start) * 1000),
        k=limit,
        corpus=corpus,
        embedding_model=embedding_model,
        filters=filters,
        top_scores=[r.get("score") for r in results[:5]],
    )


def recall(
    query: str,
    *,
    limit: int = 5,
    hybrid: bool = False,
    workspace: str | None = None,
    session=None,
    embedding_service=None,
    surface: str | None = None,
    corpus: str = "brain",
) -> list[dict]:
    """Dispatch exact-id -> semantic/hybrid exactly as `query_brain.main()` does.

    A single typed entry point so the `syn recall` CLI and (later) MCP tools
    share one implementation with the manual `query_brain.py` script instead
    of reimplementing the exact-id / semantic / hybrid dispatch order.

    Args:
        query: Natural-language question (or a bare structured ID) to search.
        limit: Maximum number of results to return.
        hybrid: When True, use `hybrid_search` (the promoted retrieval-engine
            fusion pipeline) instead of the raw exact-id / semantic-search
            dispatch.
        workspace: Optional workspace name to scope results to a `project`
            (D47) — resolved to `filters={"project": workspace}` and threaded
            into every path (exact-id, semantic, hybrid). Left unapplied
            (`None`) so default behavior is unchanged when unset.
        session: An open SQLAlchemy session (injected; opened via
            `database.session.db_session` when omitted and not `hybrid`).
        embedding_service: An `EmbeddingService` instance (injected; built
            lazily when omitted and needed).
        surface: Optional calling-surface tag (`"cli"` / `"http"` /
            `"workflow"` / `"eval"` / `"mcp"`) for the OR.K1 query log
            (`app/brain/query_log.py`). `None` (the default) is logged as
            `"unknown"`; has no effect on retrieval behavior.
        corpus: Corpus to query — `"brain"` (default), `"content"`, or
            `"code"` (OR.P). Keyword-only with default `"brain"` so every
            existing caller is unchanged. Every path is now corpus-exclusive
            (`SY.ticket.recall-corpus-exclusivity`): exact-id lookup stays
            `"brain"`-only (structured IDs like `D20`/`OR.V` are a
            brain-corpus concept), and non-hybrid semantic search for any
            other corpus is scoped to that corpus's own table via
            `retrieval_engine._CORPUS_CONFIG` (`_semantic_search_corpus`)
            instead of falling back to `BrainDocument`.

    Returns:
        A list of normalized result dicts, one shape on every path:
        `{doc_id, file_path, title, section, content, score, via}`, with
        `score` a similarity where higher is better on every path.
    """
    if hybrid:
        return hybrid_search(
            query,
            limit=limit,
            workspace=workspace,
            session=session,
            surface=surface,
            corpus=corpus,
        )

    start = time.monotonic()

    owns_session = session is None
    if owns_session:
        from database.session import (  # pylint: disable=import-outside-toplevel
            db_session as _db_session,
        )

        session = next(_db_session())

    filters = _workspace_filters(workspace)

    # Exact-id lookup is a brain-corpus concept — structured IDs like "D20"
    # or "OR.V" identify brain_documents rows, not code/content chunks — so
    # it is scoped to corpus="brain" only. A non-brain corpus always goes
    # through the corpus-scoped semantic path below, even for a query that
    # happens to contain an ID-shaped token.
    exact_id = find_exact_id(query) if corpus == "brain" else None
    if exact_id is not None:
        id_results = exact_id_lookup(exact_id, session, limit=limit, filters=filters)
        results = [_normalize_doc_row(doc, 1.0, via="exact-id") for doc in id_results]
        _log_recall(
            query,
            results,
            workspace=workspace,
            surface=surface,
            start=start,
            limit=limit,
            filters=filters,
            corpus=corpus,
        )
        return results

    if embedding_service is None:
        from services.embedding_service import (  # pylint: disable=import-outside-toplevel
            EmbeddingService,
        )

        embedding_service = EmbeddingService()

    if corpus == "brain":
        results = semantic_search(query, session, embedding_service, limit=limit, filters=filters)
        normalized = [
            _normalize_doc_row(doc, 1.0 - distance, via="semantic") for doc, distance in results
        ]
    else:
        normalized = _semantic_search_corpus(
            query, session, embedding_service, corpus, limit=limit, filters=filters
        )
    _log_recall(
        query,
        normalized,
        workspace=workspace,
        surface=surface,
        start=start,
        limit=limit,
        filters=filters,
        embedding_model=getattr(embedding_service, "stamp", None),
        corpus=corpus,
    )
    return normalized
