"""GET /recall, /walk, /pulse router — the read half of the D51 HTTP adapter
whose write half is ``app/api/ingest.py``.

Mounts three thin, authenticated GET routes over the ``app.brain`` read core
(OR.N1): ``retrieval.recall``, ``graph.walk``, and ``pulse.pulse``. Each
route opens no session of its own (``Depends(db_session)`` injected), issues
no direct SQL, and adds no second retrieval/traversal implementation —
ranking, fusion, and traversal output stay byte-identical to what
``syn recall`` / ``syn walk`` / ``syn pulse`` return today.
"""

from brain import graph, retrieval
from brain import pulse as pulse_core
from database.session import db_session
from fastapi import APIRouter, Depends, HTTPException, Query
from schemas.read_schema import PulseResponse, RecallResponse, WalkResponse
from sqlalchemy.orm import Session

from api.security import require_api_key

router = APIRouter()


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
        HTTPException: 500 if the underlying recall core raises.
    """
    try:
        results = retrieval.recall(
            q, limit=limit, hybrid=hybrid, session=session, surface="http"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Recall failed: {exc}") from exc

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
        HTTPException: 500 if the underlying walk core raises.
    """
    try:
        result = graph.walk(doc_id, depth=depth, session=session)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Walk failed: {exc}") from exc

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
        HTTPException: 500 if the underlying pulse core raises.
    """
    try:
        report = pulse_core.pulse(session=session)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pulse failed: {exc}") from exc

    return PulseResponse(**report.to_dict())
