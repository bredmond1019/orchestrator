"""ConsolidationNode — dream-time, deep-reasoning consolidation pass.

An ``AgentNode`` subclass that reasons across each peer's recent
``AgentEpisode`` rows, current ``SemanticMemory`` facts, and prior
``representation`` (as loaded by ``LoadMemoryContextNode``) to produce, per
peer: a refreshed durable ``representation`` and a set of durable facts —
some brand new, some superseding an existing fact by
``contradicts_fact_id`` (the never-overwrite contradiction rule is enforced
downstream by ``UpsertMemoryNode``; this node only *proposes* which existing
fact id a new fact contradicts).

The system prompt is loaded from ``app/prompts/memory_consolidation.j2`` via
``PromptManager`` — no system prompt is hardcoded here (CLAUDE.md rule 2).
``run_agent_recorded`` is used so per-node telemetry is captured for the data
contract (D30).

**D35 guard (frontier-only rule):** dream-time consolidation must stay on
Claude, never a local model — weak models produce confident-but-wrong
durable facts. ``get_agent_config()`` below pins ``ModelProvider.CLAUDE_CODE_SDK``;
``tests/workflows/test_memory_consolidation_workflow.py`` asserts this
directly so a config drift to a local model fails CI. Unlike ingest-time
extraction (which *is* a local-model routing candidate for OR.U/Project H),
this node has no such exemption — do not change ``model_provider`` here
without updating D35.
"""

import json

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import BaseModel, Field
from services.prompt_loader import PromptManager


class ConsolidationNode(AgentNode):
    """Agent node that consolidates episodes + facts into durable memory, per peer."""

    class ConsolidatedFact(BaseModel):
        """One durable fact this consolidation pass proposes writing."""

        fact: str = Field(description="The fact text, written as a standalone statement")
        confidence: float | None = Field(
            default=None, description="Confidence in this fact (0-1), or null for the default"
        )
        contradicts_fact_id: str | None = Field(
            default=None,
            description=(
                "The id of an existing SemanticMemory fact (from the loaded context) that "
                "this new fact supersedes, or null if it does not contradict anything"
            ),
        )
        evidence_episode_ids: list[str] = Field(
            default_factory=list,
            description="Episode ids (from the loaded context) that support this fact",
        )

    class PeerConsolidation(BaseModel):
        """One peer's consolidated result."""

        peer_id: str = Field(description="The peer this consolidation result is about")
        representation: str = Field(
            description="Refreshed durable summary of everything known about this peer"
        )
        facts: list["ConsolidationNode.ConsolidatedFact"] = Field(
            default_factory=list, description="Durable facts to write for this peer"
        )

    class OutputType(AgentNode.OutputType):
        """Structured output: one consolidated result per peer, keyed by peer_id."""

        peers: list["ConsolidationNode.PeerConsolidation"] = Field(
            default_factory=list,
            description="Per-peer consolidation results; peers stay isolated from each other",
        )

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("memory_consolidation"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="opus",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Consolidate the loaded per-peer context into durable memory.

        Reads:
          - ``task_context.get_node_output("LoadMemoryContextNode")["result"]``:
            ``{"workspace_id", "peers": [{"peer_id", "peer_type",
            "representation", "episodes": [...], "facts": [...]}, ...]}``.

        Writes:
          - ``ConsolidationNode`` result: ``{"workspace_id": <str>, "peers":
            [{"peer_id", "representation", "facts": [...]}, ...]}`` — the
            structured per-peer consolidation output, passthrough
            ``workspace_id`` included for the downstream write node.
        """
        loaded = task_context.get_node_output("LoadMemoryContextNode")["result"]
        user_prompt = json.dumps({"peers": loaded["peers"]})
        result = self.run_agent_recorded(task_context, user_prompt)
        output = result.output

        task_context.update_node(
            node_name=self.node_name,
            result={
                "workspace_id": loaded["workspace_id"],
                "peers": [peer.model_dump() for peer in output.peers],
            },
        )
        return task_context
