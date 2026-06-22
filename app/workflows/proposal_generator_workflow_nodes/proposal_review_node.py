"""ProposalReviewNode — validates the AutomationRoadmap against Diagnostic criteria.

Reviews the roadmap produced by ``ProposalWriterNode`` against the explicit
criteria from the diagnostic alignment notes (§3) and master-plan §C:
- Names client company at least 3 times
- Contains exactly one specific, testable deliverable
- Proposes a realistic timeline (4–8 weeks for the first project)
- Avoids vague language
- Investment matches complexity

Each criterion is evaluated PASS/FAIL with a line reference. The node emits a
``verdict`` of ``"pass"`` or ``"revise"`` plus a ``criteria_results`` list.
Routed by ``ProposalReviewRouterNode``.
"""

# The AgentConfig boilerplate every AgentNode subclass must repeat trips R0801
# against sibling nodes; it is the prescribed framework pattern, not a refactor target.
# pylint: disable=duplicate-code

import json

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import Field
from services.prompt_loader import PromptManager


class CriterionResult(AgentNode.OutputType):
    """Result for a single review criterion."""

    criterion: str = Field(description="Name of the criterion being evaluated")
    verdict: str = Field(description="PASS or FAIL")
    note: str = Field(description="Brief explanation with a reference to where found/missing")


class ProposalReviewNode(AgentNode):
    """Agent node that reviews a roadmap against Diagnostic delivery criteria."""

    class OutputType(AgentNode.OutputType):
        verdict: str = Field(
            description="Overall review verdict: 'pass' if all criteria pass, 'revise' otherwise"
        )
        criteria_results: list[CriterionResult] = Field(
            description="Per-criterion PASS/FAIL results with notes"
        )
        summary: str = Field(description="Short overall assessment for the revise node to act on")

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("proposal_review"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Review the roadmap from ProposalWriterNode and record verdict."""
        roadmap = task_context.get_node_output("ProposalWriterNode")
        result = self.run_agent_recorded(task_context, json.dumps(roadmap))
        task_context.update_node(node_name=self.node_name, result=result.output)
        return task_context
