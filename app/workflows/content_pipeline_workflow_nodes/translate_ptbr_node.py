"""PT-BR translation node for the content_pipeline blog branch.

Translates the finished English blog post produced by ``ReviseNode`` into
Brazilian Portuguese (pt-BR), so a published post serves the brand's PT+EN
cadence. Terminal node of the linear blog branch
(writer -> self-critic -> revise -> translate); it has no downstream connection.
The translation prompt lives in ``app/prompts/translate_ptbr.j2``.

Ported from the site's ``claude-translator.ts`` (blog-post content type, Brazil
cultural adaptation, mixed technical terminology, formatting preserved). The
model is the top-tier default per the standing model strategy (frontier on the
first run-through); translation is a natural Project H downgrade candidate once
local/open-weight swaps are measured.
"""

# The AgentConfig boilerplate every AgentNode subclass must repeat trips R0801
# against the sibling blog nodes; it is the prescribed framework pattern, not a
# refactor target.
# pylint: disable=duplicate-code

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import BaseModel, Field
from services.prompt_loader import PromptManager


class TranslatedTerm(BaseModel):
    """One technical-term decision recorded during translation."""

    original: str = Field(description="The source English term")
    translation: str = Field(
        description="The chosen pt-BR translation, or the kept English term"
    )
    reasoning: str = Field(description="One-line reason for the choice")


class TranslatePtBrNode(AgentNode):
    """Agent node that translates a finished EN blog post into pt-BR."""

    class OutputType(AgentNode.OutputType):
        translated_title: str = Field(description="Post title in pt-BR")
        translated_body_markdown: str = Field(
            description="Full post body in pt-BR, Markdown preserved"
        )
        confidence: int = Field(
            default=80, description="Self-rated translation quality, 0-100"
        )
        cultural_notes: list[str] = Field(
            default_factory=list,
            description="Notes on any cultural-adaptation choices",
        )
        technical_terms: list[TranslatedTerm] = Field(
            default_factory=list,
            description="Non-obvious technical-term decisions",
        )

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("translate_ptbr"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        revised = task_context.get_node_output("ReviseNode")["result"]
        result = self.run_agent_recorded(task_context, revised.model_dump_json())
        task_context.update_node(node_name=self.node_name, result=result.output)
        return task_context
