"""ProposalWriterNode — generates the client-facing AutomationRoadmap deliverable.

Takes the structured scored opportunities from ``OpportunityIdentifierNode`` and
produces a full ``AutomationRoadmap`` conforming to The Diagnostic deliverable
template (four required sections: Situation & Opportunity, Ranked Candidates,
Top Workflow Profiles, Recommended First Engagement).

Honors ``event.language`` — defaults to PT for Brazilian clients.
"""

# pylint: disable=duplicate-code

import json

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from schemas.proposal_generator_schema import (
    AutomationRoadmap,
    ScoredCandidate,
    WorkflowProfile,
)
from services.prompt_loader import PromptManager


class ProposalWriterNode(AgentNode):
    """Agent node that writes the full AutomationRoadmap deliverable.

    Reads scored opportunities from OpportunityIdentifierNode, then asks the
    LLM to produce a client-facing roadmap following the four-section template.
    Language (PT or EN) is threaded through the prompt context from the event.
    """

    class OutputType(AgentNode.OutputType):
        """Structured output: the complete AutomationRoadmap."""

        situation_summary: str
        candidates: list[ScoredCandidate]
        top_profiles: list[WorkflowProfile]
        recommended_workflow: str
        engagement_scope: str
        price_range_brl: tuple[int, int]
        body_pt: str | None = None
        body_en: str | None = None

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("proposal_writer"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Produce the AutomationRoadmap from scored opportunities.

        Reads:
          - ``OpportunityIdentifierNode`` output (scored candidates + recommended)
          - ``task_context.event.language`` (PT | EN)

        Writes:
          - ``ProposalWriterNode`` result: validated ``AutomationRoadmap``
        """
        opportunity_output = task_context.get_node_output("OpportunityIdentifierNode")["result"]

        event = task_context.event
        if isinstance(event, dict):
            language = event.get("language", "PT")
        else:
            language = getattr(event, "language", "PT")

        user_prompt = json.dumps(
            {
                "language": language,
                "opportunity_output": opportunity_output,
            },
            default=str,
        )

        result = self.run_agent_recorded(task_context, user_prompt)
        raw = result.output

        # Build and validate the AutomationRoadmap — candidates are expected
        # sorted composite-desc (the OpportunityIdentifierNode guarantees this).
        roadmap = AutomationRoadmap(
            situation_summary=raw.situation_summary,
            candidates=raw.candidates,
            top_profiles=raw.top_profiles,
            recommended_workflow=raw.recommended_workflow,
            engagement_scope=raw.engagement_scope,
            price_range_brl=raw.price_range_brl,
            body_pt=raw.body_pt,
            body_en=raw.body_en,
        )

        task_context.update_node(node_name=self.node_name, result=roadmap)
        return task_context
