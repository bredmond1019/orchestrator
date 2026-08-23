"""POST /ingest/* router — the write-side seam for engine-rs hybrid workflows.

Mounts two routes over the one ``app.brain.ingest.ingest_artifact`` write
path (OR.Q):

- ``POST /ingest/proposal`` — pinned exactly to engine-rs's
  ``PersistToBrainNode`` payload (``EN.4.C``).
- ``POST /ingest/artifact`` — the generic envelope for future producers
  (``EN.5.A`` content-pipeline, ``EN.5.C`` external-intel).

Both are behind the existing ``require_api_key`` guard, unchanged.
"""

from brain.ingest import ingest_artifact
from database.session import db_session
from fastapi import APIRouter, Depends, HTTPException
from schemas.ingest_schema import ArtifactIngestPayload, IngestResponse, ProposalIngestPayload
from sqlalchemy.orm import Session

from api.security import require_api_key

router = APIRouter()


@router.post("/proposal", dependencies=[Depends(require_api_key)])
def ingest_proposal(
    payload: ProposalIngestPayload,
    session: Session = Depends(db_session),
) -> IngestResponse:
    """Ingest an engine-rs proposal artifact into ``brain_documents``.

    Maps ``company_name`` onto the ingest slice's ``project``/attribution
    fields and passes ``roadmap`` through as context; ``content`` is what
    gets chunked, embedded, and stored.

    Args:
        payload: The exact ``PersistToBrainNode`` payload engine-rs asserts.
        session: Database session injected by FastAPI dependency.

    Returns:
        IngestResponse: the artifact id and number of chunks written.

    Raises:
        HTTPException: 500 if the underlying ingest slice raises.
    """
    try:
        chunks_written = ingest_artifact(
            session,
            artifact_id=payload.artifact_id,
            doc_type=payload.doc_type,
            content=payload.content,
            section=payload.section,
            project=payload.company_name,
            title=payload.company_name,
            description=f"Proposal roadmap section for {payload.company_name}",
            authored_at=payload.authored_at,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Ingest failed: {exc}"
        ) from exc

    return IngestResponse(artifact_id=payload.artifact_id, chunks_written=chunks_written)


@router.post("/artifact", dependencies=[Depends(require_api_key)])
def ingest_artifact_route(
    payload: ArtifactIngestPayload,
    session: Session = Depends(db_session),
) -> IngestResponse:
    """Ingest a generic artifact into ``brain_documents``.

    Also accepts engine-rs's literal content-pipeline ``LearningArtifact``
    shape: when the generic ``content``/``doc_type`` fields are omitted,
    ``content`` falls back to ``digest_markdown`` and ``doc_type`` falls back
    to the literal ``"learning_artifact"``; ``title``/``description`` fall
    back to ``summary``. The LearningArtifact-only fields (``channel_type``,
    ``source_ref``, ``entities``, ``language``, ``summary``) are folded into
    the outbound ``metadata`` dict alongside any caller-supplied
    ``metadata`` (caller-supplied keys win on conflict).

    Args:
        payload: The generic artifact envelope (content-pipeline / external-
            intel producers).
        session: Database session injected by FastAPI dependency.

    Returns:
        IngestResponse: the artifact id and number of chunks written.

    Raises:
        HTTPException: 500 if the underlying ingest slice raises.
    """
    content = payload.content or payload.digest_markdown
    doc_type = payload.doc_type or "learning_artifact"
    title = payload.title or payload.summary
    description = payload.description or payload.summary

    derived_metadata: dict = {
        key: value
        for key, value in (
            ("channel_type", payload.channel_type),
            ("source_ref", payload.source_ref),
            ("entities", payload.entities),
            ("language", payload.language),
            ("summary", payload.summary),
        )
        if value is not None
    }
    # Caller-supplied metadata keys win over the derived LearningArtifact ones.
    merged_metadata = {**derived_metadata, **(payload.metadata or {})}

    try:
        chunks_written = ingest_artifact(
            session,
            artifact_id=payload.artifact_id,
            doc_type=doc_type,
            content=content,
            section=payload.section,
            project=payload.project,
            title=title,
            description=description,
            metadata=merged_metadata or None,
            authored_at=payload.authored_at,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Ingest failed: {exc}"
        ) from exc

    return IngestResponse(artifact_id=payload.artifact_id, chunks_written=chunks_written)
