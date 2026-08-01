"""Output schema for CompanyResearchNode (formerly the research_agent workflow).

``ResearchAgentEventSchema`` and the ``RESEARCH_AGENT`` workflow itself were removed
under `OR.X` cut 2 (D51 divestment). ``ResearchBriefOutput`` survives here because
``ProposalCompanyResearchNode`` (`app/workflows/proposal_generator_workflow_nodes/`)
subclasses `CompanyResearchNode` and reuses this output shape unchanged; it retires
with `PROPOSAL_GENERATOR` in `OR.X` cut 3.
"""

from pydantic import BaseModel, Field


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
