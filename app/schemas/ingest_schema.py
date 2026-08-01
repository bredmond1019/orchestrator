"""Request/response schemas for the POST /ingest/* endpoint family (OR.Q).

Two inbound shapes share the one ``app/brain/ingest.py`` write path:

- ``ProposalIngestPayload`` — pinned **exactly** to engine-rs's
  ``PersistToBrainNode`` stub (``EN.4.C``); field names must not change.
- ``ArtifactIngestPayload`` — the generic envelope for future producers
  (``EN.5.A`` content-pipeline, ``EN.5.C`` external-intel).

Both routes respond with the same ``IngestResponse``.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ProposalIngestPayload(BaseModel):
    """Inbound body for ``POST /ingest/proposal``.

    Matches engine-rs's ``PersistToBrainNode`` payload exactly — do not
    rename, reorder, or drop any required field. ``roadmap`` is the
    ``AutomationRoadmap`` JSON produced by ``proposal_generator_workflow``.
    ``authored_at`` is additive (optional, v1.5.0) — omitting it preserves
    the pre-existing behavior exactly.
    """

    artifact_id: str = Field(..., min_length=1, description="Stable proposal artifact id")
    company_name: str = Field(..., min_length=1, description="Client company name")
    doc_type: str = Field(..., min_length=1, description="Corpus doc_type category")
    section: str = Field(..., min_length=1, description="Section label for this chunk group")
    content: str = Field(..., min_length=1, description="Raw artifact text to ingest")
    roadmap: dict = Field(..., description="The AutomationRoadmap JSON payload")
    authored_at: datetime | None = Field(
        default=None,
        description="Optional caller-supplied authoring timestamp; falls back to now()",
    )


class ArtifactIngestPayload(BaseModel):
    """Inbound body for ``POST /ingest/artifact`` — the generic envelope.

    Serves producers other than the proposal pipeline (``EN.5.A``
    content-pipeline, ``EN.5.C`` external-intel).
    """

    artifact_id: str = Field(..., min_length=1, description="Stable source artifact id")
    doc_type: str = Field(..., min_length=1, description="Corpus doc_type category")
    content: str = Field(..., min_length=1, description="Raw artifact text to ingest")
    section: str | None = Field(default=None, description="Optional section label")
    project: str | None = Field(default=None, description="Optional OKF project slug")
    title: str | None = Field(default=None, description="Optional OKF title")
    description: str | None = Field(default=None, description="Optional OKF description")
    metadata: dict | None = Field(default=None, description="Optional free-form metadata")
    authored_at: datetime | None = Field(
        default=None,
        description="Optional caller-supplied authoring timestamp; falls back to now()",
    )


class IngestResponse(BaseModel):
    """Success response body for both ingest routes."""

    artifact_id: str = Field(..., description="Echoes the ingested artifact's id")
    chunks_written: int = Field(..., description="Number of brain_documents rows written")
