"""IngestTimeExtractionNode — fast, per-interaction extraction for the memory ingest path.

An ``AgentNode`` subclass that reads the raw interaction text from the
inbound ``MemoryIngestEventSchema`` event and extracts a structured record:
an episode summary, an outcome classification, free-form tags, and a list of
durable facts (each optionally flagged as contradicting a prior fact via
``contradicts_hint``).

The system prompt is loaded from ``app/prompts/memory_ingest_extraction.j2``
via ``PromptManager`` — no system prompt is hardcoded here (CLAUDE.md rule
2). ``run_agent_recorded`` is used so per-node telemetry is captured for the
data contract (D30).

Per block OR.S design decision 5 and the D35 frontier-only rule, dream-time
*consolidation* must stay on Claude — ingest-time *extraction* has no such
constraint and is an explicit local-model routing candidate for
``OR.U``/Project H to evaluate later (CLAUDE.md standing rule 5). This node
ships on the default Claude provider now; swapping the provider later is a
pure ``get_agent_config()`` change, never an ``if`` in ``process()``.
"""

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import BaseModel, Field
from services.prompt_loader import PromptManager


class IngestTimeExtractionNode(AgentNode):
    """Agent node that extracts an episode + candidate facts from one interaction."""

    class Fact(BaseModel):
        """One candidate durable fact extracted from the interaction."""

        fact: str = Field(description="The fact text, written as a standalone statement")
        contradicts_hint: str | None = Field(
            default=None,
            description=(
                "Short description of a prior fact this appears to contradict or "
                "supersede, or null if it does not"
            ),
        )

    class OutputType(AgentNode.OutputType):
        """Structured output: episode summary, outcome, tags, and candidate facts."""

        episode_summary: str = Field(description="Concise summary of what happened")
        outcome: str | None = Field(
            default=None, description="Short outcome classification, or null"
        )
        tags: list[str] = Field(
            default_factory=list, description="Free-form topic tags surfaced in the interaction"
        )
        facts: list["IngestTimeExtractionNode.Fact"] = Field(
            default_factory=list, description="Durable facts learned about the entity"
        )

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("memory_ingest_extraction"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Extract an episode + candidate facts from the inbound interaction text.

        Reads:
          - ``task_context.event``: ``MemoryIngestEventSchema`` — ``interaction``,
            ``workspace_id``, ``peer_id``, ``peer_type``, ``session_id``.

        Writes:
          - ``IngestTimeExtractionNode`` result: the extracted
            ``episode_summary``/``outcome``/``tags``/``facts`` plus the
            passthrough ``workspace_id``/``peer_id``/``peer_type``/``session_id``
            the downstream write node needs.
        """
        event = task_context.event
        result = self.run_agent_recorded(task_context, event.interaction)
        output = result.output

        task_context.update_node(
            node_name=self.node_name,
            result={
                "workspace_id": event.workspace_id,
                "peer_id": event.peer_id,
                "peer_type": event.peer_type,
                "session_id": event.session_id,
                "episode_summary": output.episode_summary,
                "outcome": output.outcome,
                "tags": output.tags,
                "facts": [fact.model_dump() for fact in output.facts],
            },
        )
        return task_context
