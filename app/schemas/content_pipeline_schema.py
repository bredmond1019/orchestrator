"""Event schema for the content_pipeline (Project A) workflow."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ContentPipelineEventSchema(BaseModel):
    """Inbound event for the content pipeline.

    A YouTube or article URL to ingest, plus a flag controlling whether a blog
    draft is generated. `artifact_id` is the stable identity used when the
    LearningArtifact is persisted; `timestamp` records ingestion time.
    """

    artifact_id: UUID = Field(
        default_factory=uuid4,
        description="Stable identity for the resulting LearningArtifact",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Time when the content was submitted for ingestion",
    )
    url: str = Field(..., description="YouTube or article URL to ingest")
    make_blog: bool = Field(
        default=False,
        description="When true, generate a self-corrected blog draft",
    )
