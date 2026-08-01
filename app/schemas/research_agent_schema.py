"""Output schema for CompanyResearchNode (formerly the research_agent workflow).

``ResearchAgentEventSchema`` and the ``RESEARCH_AGENT`` workflow itself were removed
under `OR.X` cut 2 (D51 divestment). ``ProposalCompanyResearchNode``, the only
remaining subclass of ``CompanyResearchNode`` reusing this output shape, was removed
under `OR.X` cut 3 along with `PROPOSAL_GENERATOR`. ``ResearchBriefOutput`` is now
unused pending `CompanyResearchNode` itself being revisited — kept only for the base
node's own tests, not for any workflow.
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
