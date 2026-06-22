"""Event and output schemas for the proposal_generator (Project C) workflow."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class ProposalGeneratorEventSchema(BaseModel):
    """Inbound event for the proposal generator workflow.

    Accepts client context from a DiagnosticIntakeOutput-style intake and
    produces a client-facing AutomationRoadmap in Portuguese or English.
    """

    company_name: str = Field(
        ...,
        description="Name of the client company",
    )
    industry: str = Field(
        ...,
        description="Industry or sector the company operates in",
    )
    description: str = Field(
        ...,
        description="Short description of the company's business and context",
    )
    language: Literal["EN", "PT"] = Field(
        default="PT",
        description="Output language: PT (Portuguese/Brazilian) or EN (English)",
    )
    intake_notes: str | None = Field(
        default=None,
        description="Optional raw notes from a DiagnosticIntakeOutput to enrich research",
    )
    artifact_id: UUID = Field(
        default_factory=uuid4,
        description="Stable identity for the resulting roadmap artifact",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Time when the proposal request was submitted",
    )


class ScoredCandidate(BaseModel):
    """A scored automation opportunity candidate.

    Scoring formula (binding constraint from diagnostic-alignment notes §3):
        composite = (frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)

    All axis scores are on a 1–5 scale per rubric anchors embedded in the
    prompt template, not enforced here (the .j2 carries the anchor text).
    """

    name: str = Field(..., description="Short name for this automation opportunity")
    problem_statement: str = Field(
        ..., description="What problem or pain point this opportunity addresses"
    )
    proposed_solution: str = Field(
        ..., description="High-level description of the proposed automation solution"
    )
    estimated_value: str = Field(
        ..., description="Human-readable estimated business value or ROI statement"
    )
    build_complexity: str = Field(
        ..., description="Human-readable complexity estimate (Low / Medium / High)"
    )
    frequency: float = Field(..., ge=1.0, le=5.0, description="How often the process runs (1–5)")
    time_cost: float = Field(
        ..., ge=1.0, le=5.0, description="Time or cost burden of the process (1–5)"
    )
    buildability: float = Field(
        ..., ge=1.0, le=5.0, description="Ease of automation build (1–5)"
    )
    composite: float = Field(
        ...,
        description=(
            "Composite score: (frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)"
        ),
    )

    @model_validator(mode="after")
    def validate_composite(self) -> "ScoredCandidate":
        """Validate that composite matches the binding formula."""
        expected = (self.frequency * 0.35) + (self.time_cost * 0.40) + (self.buildability * 0.25)
        if abs(self.composite - expected) > 0.001:
            raise ValueError(
                f"composite {self.composite} does not match formula result {expected:.4f}; "
                "use (frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)"
            )
        return self


# Keep backward-compatible alias so nodes may refer to either name.
Opportunity = ScoredCandidate


class WorkflowProfile(BaseModel):
    """Detailed profile for a top-ranked automation workflow recommendation."""

    name: str = Field(..., description="Name of the proposed workflow / automation")
    current_state: str = Field(
        ..., description="Description of the current manual or inefficient process"
    )
    proposed_solution: str = Field(
        ..., description="Description of the proposed automated solution"
    )
    stack: list[str] = Field(
        ..., description="Technology stack / tools required (non-empty)"
    )
    rough_scope_weeks: tuple[int, int] = Field(
        ..., description="Estimated delivery window (min_weeks, max_weeks)"
    )
    roi_hrs_per_week: float = Field(
        ..., description="Estimated hours recovered per week post-automation"
    )


class AutomationRoadmap(BaseModel):
    """Deliverable output of the proposal_generator workflow.

    Conforms to The Diagnostic deliverable template (notes §3):
    - Section 1: Situation & Opportunity (situation_summary)
    - Section 2: Ranked candidate table (candidates, sorted composite-desc)
    - Section 3: Top workflow profiles (top_profiles, exactly 3 or all if fewer)
    - Section 4: Recommended first engagement (recommended_workflow, engagement_scope,
                  price_range_brl)
    """

    situation_summary: str = Field(
        ..., description="Prose summary of the client's situation and key opportunities"
    )
    candidates: list[ScoredCandidate] = Field(
        ...,
        min_length=1,
        description="Scored automation candidates sorted by composite score descending",
    )
    top_profiles: list[WorkflowProfile] = Field(
        ...,
        description="Detailed profiles for the top candidates (at most 3, or all if fewer)",
    )
    recommended_workflow: str = Field(
        ..., description="Name of the single recommended first-engagement workflow"
    )
    engagement_scope: str = Field(
        ..., description="Description of the recommended first engagement scope"
    )
    price_range_brl: tuple[int, int] = Field(
        ..., description="Estimated price range in BRL (min, max)"
    )
    body_pt: str | None = Field(
        default=None, description="Full Portuguese prose body (filled by ProposalWriterNode)"
    )
    body_en: str | None = Field(
        default=None, description="Full English prose body (filled by ProposalWriterNode)"
    )

    @model_validator(mode="after")
    def validate_candidates_sorted(self) -> "AutomationRoadmap":
        """Candidates must be sorted by composite score descending."""
        scores = [c.composite for c in self.candidates]
        if scores != sorted(scores, reverse=True):
            raise ValueError(
                "candidates must be sorted by composite score descending; "
                "sort before constructing AutomationRoadmap"
            )
        return self

    @model_validator(mode="after")
    def validate_top_profiles_limit(self) -> "AutomationRoadmap":
        """top_profiles must contain at most 3 entries."""
        if len(self.top_profiles) > 3:
            raise ValueError(
                f"top_profiles may contain at most 3 entries; got {len(self.top_profiles)}"
            )
        return self
