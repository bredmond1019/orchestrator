"""ProposalReviseNode — revises the AutomationRoadmap based on review feedback.

Addresses the specific criteria failures identified by ``ProposalReviewNode``
and produces a corrected ``AutomationRoadmap`` JSON payload. This node flows
strictly to ``StorageNode``; there is no loop-back to review, keeping the DAG
acyclic per ``WorkflowValidator``.
"""

# The AgentConfig boilerplate every AgentNode subclass must repeat trips R0801
# against sibling nodes; it is the prescribed framework pattern, not a refactor target.
# pylint: disable=duplicate-code

import json

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import Field
from services.prompt_loader import PromptManager


class ProposalReviseNode(AgentNode):
    """Agent node that revises a proposal roadmap to address review feedback."""

    class OutputType(AgentNode.OutputType):
        situation_summary: str = Field(description="Revised situation and opportunity summary")
        candidates_json: str = Field(
            description=(
                "JSON array of ScoredCandidate objects, sorted composite-descending, "
                "same structure as the original roadmap"
            )
        )
        top_profiles_json: str = Field(
            description="JSON array of WorkflowProfile objects (at most 3)"
        )
        recommended_workflow: str = Field(
            description="Name of the single recommended first-engagement workflow"
        )
        engagement_scope: str = Field(
            description="Revised engagement scope — must include a 4–8 week timeline reference"
        )
        price_range_brl_min: int = Field(description="Revised minimum price in BRL")
        price_range_brl_max: int = Field(description="Revised maximum price in BRL")
        body_pt: str | None = Field(
            default=None, description="Revised Portuguese prose body (if language is PT)"
        )
        body_en: str | None = Field(
            default=None, description="Revised English prose body (if language is EN)"
        )
        revision_notes: str = Field(
            description="Short explanation of what was changed and why"
        )

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("proposal_revise"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Revise the roadmap by addressing all criteria failures from review."""
        original_roadmap = task_context.get_node_output("ProposalWriterNode")
        review_result = task_context.get_node_output("ProposalReviewNode")

        def _serialize(obj):
            """Recursively serialize dicts, handling nested Pydantic models."""
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            return str(obj)

        user_prompt = json.dumps(
            {
                "original_roadmap": _serialize(original_roadmap),
                "review_result": _serialize(review_result),
                "event": {
                    "company_name": task_context.event.company_name,
                    "industry": task_context.event.industry,
                    "language": task_context.event.language,
                },
            }
        )
        result = self.run_agent_recorded(task_context, user_prompt)
        task_context.update_node(node_name=self.node_name, result=result.output)
        return task_context
