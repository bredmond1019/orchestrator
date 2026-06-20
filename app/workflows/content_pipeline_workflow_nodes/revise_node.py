"""Revise node for the content_pipeline blog branch.

Applies the ``SelfCriticNode`` critique to the ``BlogWriterNode`` draft and
produces the revised post. Terminal node of the linear blog branch
(writer -> self-critic -> revise); it has no downstream connection. The
revision prompt lives in ``app/prompts/blog_reviser.j2``.
"""

# The AgentConfig boilerplate every AgentNode subclass must repeat trips R0801
# against the sibling blog nodes; it is the prescribed framework pattern, not a
# refactor target.
# pylint: disable=duplicate-code

import json

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import Field
from services.prompt_loader import PromptManager


class ReviseNode(AgentNode):
    """Agent node that revises a draft blog post against a critique."""

    class OutputType(AgentNode.OutputType):
        title: str = Field(description="Revised (or unchanged) post title")
        body_markdown: str = Field(description="Full revised post body in Markdown")

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("blog_reviser"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.ANTHROPIC,
            model_name="claude-opus-4-8",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        draft = task_context.get_node_output("BlogWriterNode")["result"]
        critique = task_context.get_node_output("SelfCriticNode")["result"]
        user_prompt = json.dumps(
            {
                "draft": draft.model_dump(mode="json"),
                "critique": critique.model_dump(mode="json"),
            }
        )
        result = self.run_agent_recorded(task_context, user_prompt)
        task_context.update_node(node_name=self.node_name, result=result.output)
        return task_context
