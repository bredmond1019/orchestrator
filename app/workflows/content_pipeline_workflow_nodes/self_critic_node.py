"""Self-critic node for the content_pipeline blog branch.

Critiques the draft produced by ``BlogWriterNode`` for clarity, accuracy
against the source summary, voice consistency, and structure. Second node of
the linear blog branch (writer -> self-critic -> revise). The critique prompt
lives in ``app/prompts/blog_self_critic.j2``.
"""

# The AgentConfig boilerplate every AgentNode subclass must repeat trips R0801
# against the sibling blog nodes; it is the prescribed framework pattern, not a
# refactor target.
# pylint: disable=duplicate-code

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import Field
from services.prompt_loader import PromptManager


class SelfCriticNode(AgentNode):
    """Agent node that critiques a draft blog post."""

    class OutputType(AgentNode.OutputType):
        critique: str = Field(description="Short overall assessment of the draft")
        issues: list[str] = Field(
            default_factory=list,
            description="Concrete, actionable problems found in the draft",
        )
        approved: bool = Field(
            default=False,
            description="True only when the draft has no material issues",
        )

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("blog_self_critic"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        draft = task_context.get_node_output("BlogWriterNode")["result"]
        result = self.run_agent_recorded(task_context, draft.model_dump_json())
        task_context.update_node(node_name=self.node_name, result=result.output)
        return task_context
