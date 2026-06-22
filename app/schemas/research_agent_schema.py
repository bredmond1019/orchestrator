"""Event and output schemas for the research_agent (Project B) workflow."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ResearchAgentEventSchema(BaseModel):
    """Inbound event for the research agent.

    A company name to research, plus a stable identity and submission timestamp
    mirroring the ContentPipelineEventSchema pattern.
    """

    company_name: str = Field(
        ...,
        description="Name of the company to research",
    )
    artifact_id: UUID = Field(
        default_factory=uuid4,
        description="Stable identity for the resulting research brief",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Time when the research request was submitted",
    )


class ResearchBriefOutput(BaseModel):
    """Structured research brief shaped toward the diagnostic intake schema.

    This is the thin-cut deliverable. The hardened version (Phase 1 B,
    hardened) will widen this toward ``DiagnosticIntakeOutput`` /
    ``WorkflowCandidate`` and add ``EmbeddingService`` + ``BrainDocument``
    storage (out of scope here).
    """

    company_name: str = Field(
        ...,
        description="Name of the company researched",
    )
    what_they_do: str = Field(
        ...,
        description="Short description of the company's business and market",
    )
    likely_time_sinks: list[str] = Field(
        ...,
        min_length=1,
        description="Processes where the company likely bleeds time (non-empty)",
    )
    automation_hypothesis: str = Field(
        ...,
        description="One concrete hypothesis for where automation would have the highest ROI",
    )
