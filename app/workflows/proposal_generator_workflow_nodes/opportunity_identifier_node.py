"""OpportunityIdentifierNode — scores automation opportunities against the Diagnostic rubric.

Reads research evidence from CompanyResearchNode output in TaskContext, emits exactly
three scored candidates using the binding composite formula:

    composite = (frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)

Rubric axis anchors live in the .j2 prompt, not in this file, so scoring remains
model-version-stable without Python changes.
"""

# The AgentConfig boilerplate that every AgentNode subclass must repeat trips R0801
# against sibling nodes; it is the prescribed framework pattern, not a refactor target.
# pylint: disable=duplicate-code

import json
import logging

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import Field
from schemas.proposal_generator_schema import ScoredCandidate
from services.prompt_loader import PromptManager

log = logging.getLogger(__name__)


class OpportunityIdentifierNode(AgentNode):
    """Agent node that identifies and scores three automation opportunities.

    Reads the CompanyResearchNode's research brief from TaskContext, asks the
    model to score three candidates against the Diagnostic rubric, validates
    the composite formula, and writes the sorted candidates plus the recommended
    opportunity name to the context.
    """

    class OutputType(AgentNode.OutputType):
        """Structured output: three scored candidates (composite-desc) + recommendation."""

        candidates: list[ScoredCandidate] = Field(
            description="Three scored automation candidates, sorted composite-desc",
            min_length=1,
        )
        recommended: str = Field(
            description="Name of the single recommended (highest-priority) opportunity",
        )

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("proposal_opportunity_identifier"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Read research context, score opportunities, and write results."""
        event = task_context.event
        if isinstance(event, dict):
            company_name = event.get("company_name", "")
            industry = event.get("industry", "")
            description = event.get("description", "")
            intake_notes = event.get("intake_notes")
        else:
            company_name = getattr(event, "company_name", "")
            industry = getattr(event, "industry", "")
            description = getattr(event, "description", "")
            intake_notes = getattr(event, "intake_notes", None)

        research_output = task_context.get_node_output("CompanyResearchNode")
        research_brief = research_output.get("brief", {})

        payload = {
            "company_name": company_name,
            "industry": industry,
            "description": description,
            "research_brief": research_brief,
            "intake_notes": intake_notes,
        }
        user_prompt = json.dumps(payload, ensure_ascii=False, default=str)

        result = self.run_agent_recorded(task_context, user_prompt)
        output = result.output

        log.info(
            "OpportunityIdentifierNode produced %d candidates; recommended: %s",
            len(output.candidates),
            output.recommended,
        )

        task_context.update_node(
            self.node_name,
            candidates=[c.model_dump() for c in output.candidates],
            recommended=output.recommended,
        )
        return task_context
