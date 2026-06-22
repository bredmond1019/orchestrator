"""ProposalCompanyResearchNode — adapts Project B CompanyResearchNode for the proposal pipeline.

Subclasses ``CompanyResearchNode`` from the research_agent workflow (Project B) without
modifying that file. Adapts the initial messages to consume ``ProposalGeneratorEventSchema``
fields (``company_name``, ``industry``, ``description``, ``intake_notes``) and loads a
dedicated prompt template (``proposal_research_brief.j2``) via ``PromptManager``.

The inherited tool-use loop, tool definitions, tool dispatchers, and ``ResearchBriefOutput``
validation are reused verbatim from Project B. Research evidence is written to ``TaskContext``
under this node's output key (``ProposalCompanyResearchNode``) using the ``brief`` sub-key,
consistent with the parent class pattern.
"""

import logging

from core.task import TaskContext
from services.prompt_loader import PromptManager

from workflows.research_agent_workflow_nodes.company_research_node import (
    CompanyResearchNode as _BaseCompanyResearchNode,
)

log = logging.getLogger(__name__)


class ProposalCompanyResearchNode(_BaseCompanyResearchNode):
    """Company research node adapted for the proposal_generator pipeline.

    Extends Project B's ``CompanyResearchNode`` to accept the richer context
    available in ``ProposalGeneratorEventSchema``:
    - ``company_name``: used as in the base class
    - ``industry``: passed to the .j2 template for sector-specific research focus
    - ``description``: client-supplied context
    - ``intake_notes``: optional raw notes from a DiagnosticIntakeOutput

    All tool definitions (``web_search``, ``submit_research_brief``), the tool-use
    loop, and ``ResearchBriefOutput`` validation are inherited unchanged. Only the
    initial message construction is overridden to supply the richer context and
    to load ``proposal_research_brief.j2`` instead of ``research_agent_brief.j2``.
    """

    def _build_initial_messages(self, task_context: TaskContext) -> list[dict]:
        """Seed the loop with a system prompt loaded from proposal_research_brief.j2."""
        event = task_context.event
        if isinstance(event, dict):
            company_name = event.get("company_name", "")
            industry = event.get("industry", "")
            description = event.get("description", "")
            intake_notes = event.get("intake_notes") or ""
        else:
            company_name = getattr(event, "company_name", "")
            industry = getattr(event, "industry", "")
            description = getattr(event, "description", "")
            intake_notes = getattr(event, "intake_notes", None) or ""

        system_prompt = PromptManager.get_prompt(
            "proposal_research_brief",
            company_name=company_name,
            industry=industry,
            description=description,
            intake_notes=intake_notes,
        )
        user_content = (
            f"Please research the following company and produce a diagnostic brief:\n"
            f"Company: {company_name}\n"
            f"Industry: {industry}\n"
        )
        if description:
            user_content += f"Description: {description}\n"
        if intake_notes:
            user_content += f"Intake notes: {intake_notes}\n"
        user_content += f"\nSystem context:\n{system_prompt}"

        return [{"role": "user", "content": user_content}]
