"""Summarizer node for the content_pipeline workflow.

Reads the upstream fetched text (a YouTube transcript or an extracted article),
runs a top-tier Anthropic model against the ``content_summarizer`` system prompt,
and stores a structured ``SummaryOutput``. The storage node (Task 5) imports
``SummaryOutput`` from this module.
"""

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import Field
from services.prompt_loader import PromptManager

# Node names whose output may carry the fetched source text, in priority order.
# Only one of these runs per request (the source router routes to exactly one
# fetch node), so the first match wins.
_FETCH_NODE_NAMES = ("FetchTranscriptNode", "FetchArticleNode")


class SummaryOutput(AgentNode.OutputType):
    """Structured summary produced for every ingested artifact.

    Stored on the ``LearningArtifact`` and rendered into the personal digest.
    ``category`` is a free string classified into a small starting taxonomy
    (``ai_engineering``/``physics_relativity``/``music``/``other``) rather than
    a rigid enum, so new threads can be labelled without a schema change.
    """

    title: str = Field(description="Clean, human-readable title for the artifact")
    category: str = Field(
        description=(
            "Single free-form category string; prefer one of "
            "ai_engineering/physics_relativity/music/other"
        )
    )
    tl_dr: str = Field(description="One-line core takeaway")
    read_time_estimate: str = Field(
        description="Short human read-time estimate, e.g. '6 min'"
    )
    core_concepts: list[str] = Field(
        default_factory=list, description="Key ideas the source teaches"
    )
    key_insights: list[str] = Field(
        default_factory=list, description="Non-obvious, memorable points worth retaining"
    )
    questions_raised: list[str] = Field(
        default_factory=list, description="Open questions the source provokes"
    )
    connections_to_my_work: list[str] = Field(
        default_factory=list,
        description="Explicit links to Brandon's agentic-engineering / AI-architecture work",
    )
    further_exploration: list[str] = Field(
        default_factory=list, description="Concrete next things to read, watch, or try"
    )


class SummarizerNode(AgentNode):
    """Agent node that turns fetched source text into a ``SummaryOutput``."""

    OutputType = SummaryOutput

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("content_summarizer"),
            output_type=SummaryOutput,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def _read_source_text(self, task_context: TaskContext) -> str:
        """Pull the fetched text from whichever fetch node ran upstream.

        Returns an empty string if no fetch node produced text (e.g. a failed
        fetch) so the agent still runs and can summarize the absence rather than
        crashing the pipeline.
        """
        for node_name in _FETCH_NODE_NAMES:
            node_output = task_context.nodes.get(node_name)
            if node_output and node_output.get("text"):
                return node_output["text"]
        return ""

    def process(self, task_context: TaskContext) -> TaskContext:
        source_text = self._read_source_text(task_context)
        result = self.run_agent_recorded(task_context, source_text)
        task_context.update_node(node_name=self.node_name, result=result.output)
        return task_context
