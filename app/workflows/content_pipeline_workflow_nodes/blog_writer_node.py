"""Blog writer node for the content_pipeline workflow.

Drafts a blog post in Brandon's voice from the structured ``SummaryOutput``
produced by the summarizer. First node of the linear blog branch
(writer -> self-critic -> revise). The voice guidance lives in
``app/prompts/blog_writer.j2`` and is a long-term asset reused by Project C.
"""

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import Field
from services.prompt_loader import PromptManager


class BlogWriterNode(AgentNode):
    """Agent node that turns a ``SummaryOutput`` into a draft blog post."""

    class OutputType(AgentNode.OutputType):
        title: str = Field(description="Clear, specific title for the blog post")
        body_markdown: str = Field(description="Full post body in Markdown")
        reasoning: str = Field(
            description="Short note on the chosen angle and structure"
        )

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("blog_writer"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        summary = task_context.get_node_output("SummarizerNode")["result"]
        result = self.run_agent_recorded(task_context, summary.model_dump_json())
        task_context.update_node(node_name=self.node_name, result=result.output)
        return task_context
