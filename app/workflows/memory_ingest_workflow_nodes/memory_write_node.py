"""MemoryWriteNode — terminal write step of the memory ingest path.

Composes the two standalone ``app/memory/`` building blocks (block OR.S
design decision 1) in the order the fast, per-interaction pipeline needs:

1. ``EpisodeWriteService.write(...)`` — persist one ``AgentEpisode`` for the
   interaction, upserting the owning ``Peer`` (creates it on first sight of
   ``(workspace_id, peer_id)``, otherwise reuses it — the accumulation
   acceptance criterion's foundation).
2. ``UpsertMemoryNode.upsert_facts(...)`` — write the extracted candidate
   facts as ``SemanticMemory`` rows, applying the never-overwrite
   contradiction rule for any fact whose ``contradicts_hint`` was resolved to
   an existing row's id.

This node itself does not talk to the database directly — it delegates to
the two memory-module seams, which are what tests monkeypatch (CLAUDE.md
standing rule 7: persistence only via ``GenericRepository``/the shared
``db_session`` seam, never ad hoc in a node).
"""

from core.nodes.base import Node
from core.task import TaskContext
from memory.episode_write_service import EpisodeWriteService
from memory.upsert_memory_node import UpsertMemoryNode


class MemoryWriteNode(Node):
    """Terminal node: write the extracted episode + facts to the memory store."""

    def __init__(
        self,
        source_node_name: str = "IngestTimeExtractionNode",
        episode_write_service: EpisodeWriteService | None = None,
        upsert_memory_node: UpsertMemoryNode | None = None,
    ):
        """``source_node_name`` is the upstream extraction node whose
        ``result`` carries the episode + candidate facts. ``episode_write_service``
        and ``upsert_memory_node`` default to fresh instances but are
        injectable so tests can supply doubles without monkeypatching two
        separate seams."""
        self.source_node_name = source_node_name
        self.episode_write_service = episode_write_service or EpisodeWriteService()
        self.upsert_memory_node = upsert_memory_node or UpsertMemoryNode()

    def process(self, task_context: TaskContext) -> TaskContext:
        """Write the episode, then upsert the extracted facts.

        Reads ``task_context.get_node_output(self.source_node_name)["result"]``
        for ``{"workspace_id", "peer_id", "peer_type", "session_id",
        "episode_summary", "outcome", "tags", "facts"}`` (CLAUDE.md standing
        rule 9 storage contract).

        Writes: ``{"episode_id": <str>, "peer_id": <str>, "upserted_fact_ids":
        [<str>, ...]}``.
        """
        source = task_context.get_node_output(self.source_node_name)["result"]

        episode = self.episode_write_service.write(
            workspace_id=source["workspace_id"],
            peer_id=source["peer_id"],
            peer_type=source["peer_type"],
            summary=source["episode_summary"],
            session_id=source.get("session_id"),
            outcome=source.get("outcome"),
            tags=source.get("tags"),
        )

        # Ingest-time extraction only surfaces a free-text `contradicts_hint`
        # (e.g. "the rate was renegotiated") — resolving that hint against an
        # existing SemanticMemory row's id is a similarity-search problem
        # deferred to dream-time consolidation (design decision 5: contradiction
        # *resolution* is the deep, dream-time pass's job). Ingest-time writes
        # candidate facts as plain new rows; UpsertMemoryNode's never-overwrite
        # contradiction path is exercised directly by MemoryConsolidationWorkflow
        # (Task 4) once it resolves a hint to a concrete `contradicts_fact_id`.
        facts = [{"fact": fact["fact"]} for fact in source.get("facts", [])]
        upserted = self.upsert_memory_node.upsert_facts(
            peer_id=source["peer_id"],
            facts=facts,
            evidence_episode_ids=[str(episode.id)],
        )

        task_context.update_node(
            node_name=self.node_name,
            result={
                "episode_id": str(episode.id),
                "peer_id": source["peer_id"],
                "upserted_fact_ids": [str(row.id) for row in upserted],
            },
        )
        return task_context
