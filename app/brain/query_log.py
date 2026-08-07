"""app/brain/query_log.py — OR.K1 fire-and-forget retrieval query log.

Writes exactly one ``retrieval_queries`` row per call into the promoted
retrieval core: ``retrieval_engine.retrieve()`` (the hybrid/full path) and
``retrieval.recall()``'s exact-id/semantic returns are the only two call
sites (CLAUDE.md standing rule 10 — the shared ``app/brain/`` service layer
accretes one slice at a time; this slice answers "what did my agents
actually ask the Brain this week, and how often did it come up empty?" with
a single table, a single write, and ``syn queries`` as the single read
command).

**Fire-and-forget discipline:** ``log_retrieval`` opens its own,
independently committed session (open -> add -> commit -> close, via
``GenericRepository`` per standing rule 7 — never a raw session write) and
swallows any exception after a ``logging.warning`` — a logging failure must
never fail or roll back the retrieval call it is describing. Mirrors the
independent-session precedent in ``worker/tasks.py::_write_failure_marker``.

**Test-suite inertness:** the write is a no-op unless the
``BRAIN_QUERY_LOG_ENABLED`` environment variable is truthy ("1"/"true",
case-insensitive). It defaults **on** so production entry points (``syn``,
the FastAPI app, the Celery worker) log without any extra configuration; the
top-level ``tests/conftest.py`` carries an autouse fixture that forces it
off for the whole suite, and ``tests/brain/conftest.py`` carries an opt-in
fixture (``enable_query_log``) that flips it back on for the tests in this
module that actually assert on written rows. The env var is read at call
time (not import time) so per-test monkeypatching works.

Deliberately **not** here: any aggregation, rollup, or dashboard. Every
statistic (e.g. an abstain rate) is computed at read time over the raw rows
by ``syn queries`` — see ``app/brain/cli.py``. The moment this module grows
an aggregation table or a scheduled job, that capability belongs in
engine-rs (the D51 guard), not here.
"""

import logging
import os
import uuid
from collections import Counter
from contextlib import contextmanager

from database.repository import GenericRepository
from database.retrieval_query import RetrievalQuery
from database.session import db_session
from schemas.document_qa_schema import DocumentQAEventSchema

# The abstain threshold is imported from its single source of truth — the
# DOCUMENT_QA event schema's `confidence_threshold` default — rather than
# re-hardcoded here, so the two never silently drift apart.
ABSTAIN_THRESHOLD: float = DocumentQAEventSchema.model_fields[  # pylint: disable=unsubscriptable-object
    "confidence_threshold"
].default

_ENABLED_TRUE_VALUES = {"1", "true"}


def _query_log_enabled() -> bool:
    """Return whether logging is active for this call, per `BRAIN_QUERY_LOG_ENABLED`.

    Checked at call time (not import time or module load) so tests can flip
    the env var per-test via `monkeypatch.setenv`. Unset defaults to
    enabled; any value other than "1"/"true" (case-insensitive) disables it.
    """
    return os.environ.get("BRAIN_QUERY_LOG_ENABLED", "1").strip().lower() in _ENABLED_TRUE_VALUES


def _session_scope():
    """Return a context manager yielding an independent SQLAlchemy session.

    Isolated so tests can monkeypatch `query_log.db_session` (the
    module-level import) to force a logging failure without touching a live
    database.
    """
    return contextmanager(db_session)()


def log_retrieval(  # pylint: disable=too-many-arguments,too-many-locals
    query: str,
    results: list[dict],
    *,
    surface: str | None,
    workspace_id: str | None,
    hybrid: bool,
    retrieval_confidence: float | None,
    latency_ms: int | None,
    k: int | None = None,
    corpus: str | None = None,
    embedding_model: str | None = None,
    filters: dict | None = None,
    top_scores: list[float] | None = None,
) -> None:
    """Write one `retrieval_queries` row describing a single retrieval call.

    Args:
        query: The raw query text passed into the retrieval core.
        results: The normalized candidate/result dicts returned by the
            call — each expected to carry `via`, `doc_id`, and `score` keys
            (the shape both `retrieval_engine.retrieve()` and
            `retrieval.recall()`'s exact-id/semantic paths already produce).
        surface: Calling surface (`"cli"` / `"http"` / `"workflow"` /
            `"mcp"` / `None`). `None` is stored as `"unknown"`.
        workspace_id: The D47 workspace the query was scoped to, if any.
        hybrid: Whether the hybrid fusion pipeline (`retrieve()`) produced
            `results`, as opposed to the exact-id/semantic dispatch paths.
        retrieval_confidence: The confidence signal computed for this call
            (e.g. `retrieval_engine.compute_retrieval_confidence`), if any.
        latency_ms: Wall-clock latency of the retrieval call, measured by
            the caller around the core call via `time.monotonic`.
        k: Requested result count for this call (OR.2.E), making
            `result_count` interpretable. Keyword-only, defaults to `None`
            so neither existing call site breaks mid-deploy.
        corpus: Corpus the query was scoped to (e.g. `"brain"`,
            `"content"`), OR.2.E. `None` by default.
        embedding_model: The `EmbeddingService.stamp` (`"{provider}:{model}"`)
            live at call time, OR.2.E. Read from the retrieval path's
            already-constructed embedder rather than building a fresh
            `EmbeddingService()` just to ask. `None` by default.
        filters: Filters applied to this retrieval call, if any (OR.2.E).
            `None` by default.
        top_scores: Top 5 candidate scores in rank order, aligned with
            `top_doc_ids` (OR.2.E). `None` by default; when omitted here
            it is derived from `results` the same way `top_doc_ids` is.

    Never raises: any failure (env flag aside) is caught, logged via
    `logging.warning`, and swallowed so the retrieval call this describes
    is never affected. Every new (OR.2.E) field is computed inside this
    same try block so a malformed value degrades the log row rather than
    escaping to the caller.
    """
    if not _query_log_enabled():
        return

    try:
        via_mix = dict(Counter(r.get("via", "unknown") for r in results))
        top_doc_ids = [r.get("doc_id") for r in results[:5] if r.get("doc_id")]
        top_score = results[0].get("score") if results else None
        abstained = retrieval_confidence is not None and retrieval_confidence < ABSTAIN_THRESHOLD
        resolved_top_scores = (
            top_scores if top_scores is not None else [r.get("score") for r in results[:5]]
        )

        row = RetrievalQuery(
            id=uuid.uuid4(),
            query=query,
            surface=surface or "unknown",
            workspace_id=workspace_id,
            hybrid=hybrid,
            via_mix=via_mix,
            result_count=len(results),
            top_score=top_score,
            retrieval_confidence=retrieval_confidence,
            abstained=abstained,
            top_doc_ids=top_doc_ids,
            latency_ms=latency_ms,
            k=k,
            corpus=corpus,
            embedding_model=embedding_model,
            filters=filters,
            top_scores=resolved_top_scores,
        )
        with _session_scope() as session:
            repository = GenericRepository(session=session, model=RetrievalQuery)
            repository.create(row)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logging.warning("retrieval query log write failed: %s", exc)
