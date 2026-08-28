"""GET /recall, /walk, /pulse router — the read half of the D51 HTTP adapter
whose write half is ``app/api/ingest.py``.

Mounts three thin, authenticated GET routes over the ``app.brain`` read core
(OR.N1): ``retrieval.recall``, ``graph.walk``, and ``pulse.pulse``. Each
route opens no session of its own (``Depends(db_session)`` injected), issues
no direct SQL, and adds no second retrieval/traversal implementation —
ranking, fusion, and traversal output stay byte-identical to what
``syn recall`` / ``syn walk`` / ``syn pulse`` return today.

Dependency-failure classification (OR.3.B task 1): an unattended engine-rs
consumer needs to tell a transient dependency outage (pgvector/Postgres or
the embedding backend unreachable — retry with backoff) apart from a genuine
internal bug (do not retry). ``_classify_dependency_failure`` walks the
exception's ``__cause__``/``__context__`` chain (so a wrapped cause is still
recognised) looking for SQLAlchemy's ``OperationalError``/``InterfaceError``
or the standard connection-error hierarchy (``ConnectionError``,
``TimeoutError``, ``OSError``). A dependency failure raises ``502`` with
``detail.error == "brain_backend_unavailable"``; anything else keeps the
existing ``500`` but with the same dict body shape (``detail.error`` set to
a route-specific ``*_failed`` key) so a consumer never has to parse prose to
branch. ``502`` was chosen deliberately over ``503``:
``api/security.py::require_api_key`` already returns ``503`` for an
unconfigured server key, and that condition is NOT retryable while a backend
outage IS — two different retry semantics must not share a status code.
"""

from typing import NoReturn

from brain import graph, retrieval
from brain import pulse as pulse_core
from database.session import db_session
from fastapi import APIRouter, Depends, HTTPException, Query
from schemas.read_schema import PulseResponse, RecallResponse, WalkResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from api.security import require_api_key

router = APIRouter()

_DEPENDENCY_ERROR_TYPES = (
    OperationalError,
    InterfaceError,
    ConnectionError,
    TimeoutError,
    OSError,
)


def _classify_dependency_failure(exc: BaseException) -> bool:
    """Return True if `exc` (or a chained cause/context) is a dependency
    failure — pgvector/Postgres or the embedding backend unreachable —
    rather than an unexpected internal error.

    Walks `__cause__`/`__context__` so a dependency error wrapped in a
    generic exception (`raise RuntimeError(...) from ConnectionError(...)`)
    is still recognised.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, _DEPENDENCY_ERROR_TYPES):
            return True
        current = current.__cause__ or current.__context__
    return False


def _raise_classified(exc: Exception, *, generic_error: str) -> NoReturn:
    """Raise the typed HTTPException for a read-core failure.

    502 `brain_backend_unavailable` for a classified dependency failure,
    else the existing 500 with a `generic_error` machine-readable key.
    """
    if _classify_dependency_failure(exc):
        raise HTTPException(
            status_code=502,
            detail={"error": "brain_backend_unavailable", "message": str(exc)},
        ) from exc
    raise HTTPException(
        status_code=500,
        detail={"error": generic_error, "message": str(exc)},
    ) from exc


@router.get("/recall", dependencies=[Depends(require_api_key)], response_model=RecallResponse)
def recall_route(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(5, ge=1, le=50, description="Maximum results to return"),
    hybrid: bool = Query(False, description="Use hybrid (semantic + structural) retrieval"),
    session: Session = Depends(db_session),
) -> RecallResponse:
    """Return `app.brain.retrieval.recall()`'s results for `q`.

    Args:
        q: The search query string.
        limit: Maximum number of results to return (default 5).
        hybrid: Whether to use hybrid retrieval (default False).
        session: Database session injected by FastAPI dependency.

    Returns:
        RecallResponse: the query, result count, and normalized results.

    Raises:
        HTTPException: 502 if a dependency (pgvector/Postgres or the
            embedding backend) is unreachable; 500 for any other
            unexpected failure from the recall core.
    """
    try:
        results = retrieval.recall(
            q, limit=limit, hybrid=hybrid, session=session, surface="http"
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Intentionally broad: any failure from the read core (dependency
        # outage or an unexpected bug) must be classified and re-raised as a
        # typed HTTPException below, never left to surface as a raw 500.
        _raise_classified(exc, generic_error="recall_failed")

    return RecallResponse(query=q, count=len(results), results=results)


@router.get("/walk", dependencies=[Depends(require_api_key)], response_model=WalkResponse)
def walk_route(
    doc_id: str = Query(..., min_length=1, description="Root document id to traverse from"),
    depth: int = Query(1, ge=1, le=5, description="Maximum number of hops to traverse"),
    session: Session = Depends(db_session),
) -> WalkResponse:
    """Return `app.brain.graph.walk()`'s traversal for `doc_id`.

    A doc with no edges returns `200` with `levels: []`, not a `404`.

    Args:
        doc_id: The root document id to traverse from.
        depth: Maximum number of hops to traverse (default 1).
        session: Database session injected by FastAPI dependency.

    Returns:
        WalkResponse: the root, depth, levels, and resolved neighbor nodes.

    Raises:
        HTTPException: 502 if a dependency (pgvector/Postgres) is
            unreachable; 500 for any other unexpected failure from the
            walk core.
    """
    try:
        result = graph.walk(doc_id, depth=depth, session=session)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Intentionally broad: see recall_route's identical justification.
        _raise_classified(exc, generic_error="walk_failed")

    return WalkResponse(**result)


@router.get("/pulse", dependencies=[Depends(require_api_key)], response_model=PulseResponse)
def pulse_route(
    session: Session = Depends(db_session),
) -> PulseResponse:
    """Return `app.brain.pulse.pulse().to_dict()`.

    Returns `200` even when `healthy` is false — the flag is the signal,
    not the status code.

    Args:
        session: Database session injected by FastAPI dependency.

    Returns:
        PulseResponse: live row counts, watermarks, and the `healthy` flag.

    Raises:
        HTTPException: 502 if a dependency (pgvector/Postgres) is
            unreachable; 500 for any other unexpected failure from the
            pulse core.
    """
    try:
        report = pulse_core.pulse(session=session)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Intentionally broad: see recall_route's identical justification.
        _raise_classified(exc, generic_error="pulse_failed")

    return PulseResponse(**report.to_dict())
