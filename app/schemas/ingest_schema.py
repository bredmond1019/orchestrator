"""Request/response schemas for the POST /ingest/* endpoint family (OR.Q).

Two inbound shapes share the one ``app/brain/ingest.py`` write path:

- ``ProposalIngestPayload`` — pinned **exactly** to engine-rs's
  ``PersistToBrainNode`` stub (``EN.4.C``); field names must not change.
- ``ArtifactIngestPayload`` — the generic envelope for future producers
  (``EN.5.A`` content-pipeline, ``EN.5.C`` external-intel).

Both routes respond with the same ``IngestResponse``.
"""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator


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
    content-pipeline, ``EN.5.C`` external-intel). Absorbs engine-rs's literal
    seven-field ``LearningArtifact`` shape (``artifact_id``, ``channel_type``,
    ``source_ref``, ``summary``, ``digest_markdown``, ``entities``,
    ``language``) alongside the pre-existing generic envelope fields —
    ``doc_type``/``content`` are now optional and fall back to
    ``"learning_artifact"``/``digest_markdown`` respectively at the route
    (``app/api/ingest.py``), so at least one of each pair must be supplied
    (enforced below). ``/ingest/learning`` has never existed; this route
    absorbs that shape instead of adding a new one.
    """

    artifact_id: str = Field(..., min_length=1, description="Stable source artifact id")
    doc_type: str | None = Field(
        default=None,
        min_length=1,
        description="Corpus doc_type category; falls back to 'learning_artifact' when omitted",
    )
    content: str | None = Field(
        default=None,
        min_length=1,
        description="Raw artifact text to ingest; falls back to digest_markdown when omitted",
    )
    section: str | None = Field(default=None, description="Optional section label")
    project: str | None = Field(default=None, description="Optional OKF project slug")
    title: str | None = Field(default=None, description="Optional OKF title")
    description: str | None = Field(default=None, description="Optional OKF description")
    metadata: dict | None = Field(default=None, description="Optional free-form metadata")
    authored_at: datetime | None = Field(
        default=None,
        description="Optional caller-supplied authoring timestamp; falls back to now()",
    )

    # engine-rs content-pipeline LearningArtifact fields (OR.3.A) — optional,
    # folded into the outbound metadata dict by the route rather than stored
    # as dedicated columns (brain_documents has no matching columns).
    channel_type: str | None = Field(
        default=None, description="LearningArtifact: producing channel (e.g. 'web_article')"
    )
    source_ref: str | None = Field(
        default=None, description="LearningArtifact: source URL/reference for the artifact"
    )
    summary: str | None = Field(
        default=None,
        description="LearningArtifact: concise summary; falls back for title/description",
    )
    digest_markdown: str | None = Field(
        default=None, description="LearningArtifact: full markdown digest; falls back for content"
    )
    entities: list[str] | None = Field(
        default=None, description="LearningArtifact: named entities extracted from the artifact"
    )
    language: str | None = Field(default=None, description="LearningArtifact: ISO language code")

    @model_validator(mode="after")
    def _require_content_and_doc_type(self) -> Self:
        """Enforce the two either/or invariants the route's fallbacks rely on.

        A body with neither ``content`` nor ``digest_markdown`` — or neither
        ``doc_type`` nor ``digest_markdown`` — has nothing for the route to
        fall back to, so it must still 422 rather than reach the write path.
        """
        if not (self.content or self.digest_markdown):
            raise ValueError("either 'content' or 'digest_markdown' must be provided")
        if not (self.doc_type or self.digest_markdown):
            raise ValueError("either 'doc_type' or 'digest_markdown' must be provided")
        return self


class IngestResponse(BaseModel):
    """Success response body for both ingest routes."""

    artifact_id: str = Field(..., description="Echoes the ingested artifact's id")
    chunks_written: int = Field(..., description="Number of brain_documents rows written")
