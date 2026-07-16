"""Tests for MemoryIngestWorkflow (block OR.S, Task 3).

Three layers:

* **Structure** — registration in ``WorkflowRegistry`` + ``SCHEMA_MAP``
  (CLAUDE.md standing rule 6), schema wiring (start node, linear two-node
  connections), ``WorkflowValidator`` acceptance.
* **Event schema** — ``MemoryIngestEventSchema`` validates the required
  fields.
* **Nodes** — ``IngestTimeExtractionNode`` with the agent seam mocked
  (no live LLM call) and ``MemoryWriteNode`` with the two memory-module
  seams (``EpisodeWriteService``, ``UpsertMemoryNode``) doubled, proving the
  ingest-time test family: extraction -> a valid episode write + fact
  upserts.

TaskContext seeds follow CLAUDE.md rule 9: upstream output is stored as
``{"result": payload}`` matching what ``update_node(node_name=..., result=...)``
writes.
"""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from core.task import TaskContext
from core.validate import WorkflowValidator
from schemas.memory_schema import MemoryIngestEventSchema
from workflows.memory_ingest_workflow import MemoryIngestWorkflow
from workflows.memory_ingest_workflow_nodes.ingest_time_extraction_node import (
    IngestTimeExtractionNode,
)
from workflows.memory_ingest_workflow_nodes.memory_write_node import MemoryWriteNode


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


class TestMemoryIngestWorkflowStructure:
    def test_start_is_ingest_time_extraction_node(self):
        assert MemoryIngestWorkflow.workflow_schema.start is IngestTimeExtractionNode

    def test_event_schema_is_memory_ingest(self):
        assert MemoryIngestWorkflow.workflow_schema.event_schema is MemoryIngestEventSchema

    def test_two_nodes_in_workflow(self):
        node_classes = {nc.node for nc in MemoryIngestWorkflow.workflow_schema.nodes}
        assert node_classes == {IngestTimeExtractionNode, MemoryWriteNode}

    def test_linear_dag_connections(self):
        node_map = {
            nc.node: nc.connections for nc in MemoryIngestWorkflow.workflow_schema.nodes
        }
        assert node_map[IngestTimeExtractionNode] == [MemoryWriteNode]
        assert node_map[MemoryWriteNode] == []

    def test_no_routers(self):
        for nc in MemoryIngestWorkflow.workflow_schema.nodes:
            assert not nc.is_router

    def test_workflow_validator_accepts_schema(self):
        validator = WorkflowValidator(MemoryIngestWorkflow.workflow_schema)
        validator.validate()  # must not raise


class TestWorkflowRegistryCompleteness:
    """CLAUDE.md standing rule 6: registered in BOTH registries."""

    def test_memory_ingest_registered_in_workflow_registry(self):
        from workflows.workflow_registry import WorkflowRegistry

        assert WorkflowRegistry.MEMORY_INGEST.value is MemoryIngestWorkflow

    def test_memory_ingest_registered_in_schema_map(self):
        from api.schema_registry import SCHEMA_MAP
        from workflows.workflow_registry import WorkflowRegistry

        assert SCHEMA_MAP[WorkflowRegistry.MEMORY_INGEST.name] is MemoryIngestEventSchema

    def test_every_workflow_has_schema_map_entry(self):
        """Guards against reintroducing the missing-registration bug for any workflow."""
        from api.schema_registry import SCHEMA_MAP
        from workflows.workflow_registry import WorkflowRegistry

        missing = [member.name for member in WorkflowRegistry if member.name not in SCHEMA_MAP]
        assert not missing


# ---------------------------------------------------------------------------
# Event schema
# ---------------------------------------------------------------------------


class TestMemoryIngestEventSchema:
    def _valid_kwargs(self, **overrides) -> dict:
        defaults = {
            "workspace_id": "acme-workspace",
            "peer_id": "client-acme",
            "peer_type": "client",
            "session_id": "session-1",
            "interaction": "Quoted Acme $150/hr for the WhatsApp automation project.",
        }
        defaults.update(overrides)
        return defaults

    def test_valid_event(self):
        event = MemoryIngestEventSchema(**self._valid_kwargs())
        assert event.workspace_id == "acme-workspace"
        assert event.peer_id == "client-acme"
        assert event.peer_type == "client"
        assert event.session_id == "session-1"

    def test_session_id_optional(self):
        kwargs = self._valid_kwargs()
        kwargs.pop("session_id")
        event = MemoryIngestEventSchema(**kwargs)
        assert event.session_id is None

    def test_missing_workspace_id_raises(self):
        kwargs = self._valid_kwargs()
        kwargs.pop("workspace_id")
        with pytest.raises(ValidationError):
            MemoryIngestEventSchema(**kwargs)

    def test_missing_peer_id_raises(self):
        kwargs = self._valid_kwargs()
        kwargs.pop("peer_id")
        with pytest.raises(ValidationError):
            MemoryIngestEventSchema(**kwargs)

    def test_missing_interaction_raises(self):
        kwargs = self._valid_kwargs()
        kwargs.pop("interaction")
        with pytest.raises(ValidationError):
            MemoryIngestEventSchema(**kwargs)


# ---------------------------------------------------------------------------
# IngestTimeExtractionNode
# ---------------------------------------------------------------------------


def _make_extraction_node() -> IngestTimeExtractionNode:
    """Construct IngestTimeExtractionNode without building a real Agent."""
    node = IngestTimeExtractionNode.__new__(IngestTimeExtractionNode)
    node.agent = MagicMock()
    return node


def _extraction_result(
    episode_summary: str = "Quoted Acme $150/hr for the WhatsApp automation project.",
    outcome: str | None = "quoted_rate",
    tags: list[str] | None = None,
    facts: list[dict] | None = None,
):
    if facts is None:
        facts = [{"fact": "Acme was quoted $150/hr."}]
    output = IngestTimeExtractionNode.OutputType(
        episode_summary=episode_summary,
        outcome=outcome,
        tags=tags or ["rate", "whatsapp"],
        facts=[IngestTimeExtractionNode.Fact(**fact) for fact in facts],
    )
    r = MagicMock()
    r.output = output
    r.usage.return_value = MagicMock(input_tokens=5, output_tokens=10)
    return r


def _make_event(**overrides) -> MemoryIngestEventSchema:
    defaults = {
        "workspace_id": "acme-workspace",
        "peer_id": "client-acme",
        "peer_type": "client",
        "session_id": "session-1",
        "interaction": "Quoted Acme $150/hr for the WhatsApp automation project.",
    }
    defaults.update(overrides)
    return MemoryIngestEventSchema(**defaults)


class TestIngestTimeExtractionNode:
    def test_result_stored_under_result_key(self):
        node = _make_extraction_node()
        node.agent.run_sync.return_value = _extraction_result()

        ctx = TaskContext(event=_make_event())
        node.process(ctx)

        assert "result" in ctx.nodes["IngestTimeExtractionNode"]

    def test_extracted_fields_in_result(self):
        node = _make_extraction_node()
        node.agent.run_sync.return_value = _extraction_result(
            episode_summary="Quoted Acme $150/hr.",
            outcome="quoted_rate",
            tags=["rate"],
            facts=[{"fact": "Acme was quoted $150/hr.", "contradicts_hint": None}],
        )

        ctx = TaskContext(event=_make_event())
        node.process(ctx)

        stored = ctx.nodes["IngestTimeExtractionNode"]["result"]
        assert stored["episode_summary"] == "Quoted Acme $150/hr."
        assert stored["outcome"] == "quoted_rate"
        assert stored["tags"] == ["rate"]
        assert stored["facts"] == [
            {"fact": "Acme was quoted $150/hr.", "contradicts_hint": None}
        ]

    def test_passes_through_event_addressing_fields(self):
        node = _make_extraction_node()
        node.agent.run_sync.return_value = _extraction_result()

        ctx = TaskContext(
            event=_make_event(
                workspace_id="other-workspace", peer_id="peer-2", peer_type="company"
            )
        )
        node.process(ctx)

        stored = ctx.nodes["IngestTimeExtractionNode"]["result"]
        assert stored["workspace_id"] == "other-workspace"
        assert stored["peer_id"] == "peer-2"
        assert stored["peer_type"] == "company"

    def test_empty_facts_list_is_valid(self):
        node = _make_extraction_node()
        node.agent.run_sync.return_value = _extraction_result(facts=[])

        ctx = TaskContext(event=_make_event())
        node.process(ctx)

        assert ctx.nodes["IngestTimeExtractionNode"]["result"]["facts"] == []

    def test_agent_config_uses_claude_provider(self):
        """Not the D35-mandated block (that's consolidation-only), but ingest
        should still ship on the default Claude provider per the spec."""
        from core.nodes.agent import ModelProvider

        node = IngestTimeExtractionNode.__new__(IngestTimeExtractionNode)
        config = node.get_agent_config()
        assert config.model_provider == ModelProvider.CLAUDE_CODE_SDK


# ---------------------------------------------------------------------------
# MemoryWriteNode
# ---------------------------------------------------------------------------


class _FakeEpisode:
    def __init__(self, episode_id: str):
        self.id = episode_id


class TestMemoryWriteNode:
    def _ctx_with_extraction(self, **overrides) -> TaskContext:
        defaults = {
            "workspace_id": "acme-workspace",
            "peer_id": "client-acme",
            "peer_type": "client",
            "session_id": "session-1",
            "episode_summary": "Quoted Acme $150/hr.",
            "outcome": "quoted_rate",
            "tags": ["rate"],
            "facts": [{"fact": "Acme was quoted $150/hr.", "contradicts_hint": None}],
        }
        defaults.update(overrides)
        ctx = TaskContext(event=_make_event())
        ctx.nodes["IngestTimeExtractionNode"] = {"result": defaults}
        return ctx

    def _make_node(self, episode_id="episode-1", upserted_ids=None):
        episode_write_service = MagicMock()
        episode_write_service.write.return_value = _FakeEpisode(episode_id)

        upsert_memory_node = MagicMock()
        upserted_rows = [MagicMock(id=fid) for fid in (upserted_ids or ["fact-1"])]
        upsert_memory_node.upsert_facts.return_value = upserted_rows

        node = MemoryWriteNode(
            episode_write_service=episode_write_service,
            upsert_memory_node=upsert_memory_node,
        )
        return node, episode_write_service, upsert_memory_node

    def test_writes_episode_via_episode_write_service(self):
        node, episode_write_service, _ = self._make_node()
        ctx = self._ctx_with_extraction()

        node.process(ctx)

        episode_write_service.write.assert_called_once()
        kwargs = episode_write_service.write.call_args.kwargs
        assert kwargs["workspace_id"] == "acme-workspace"
        assert kwargs["peer_id"] == "client-acme"
        assert kwargs["peer_type"] == "client"
        assert kwargs["summary"] == "Quoted Acme $150/hr."
        assert kwargs["outcome"] == "quoted_rate"
        assert kwargs["tags"] == ["rate"]

    def test_upserts_facts_via_upsert_memory_node_with_episode_evidence(self):
        node, _, upsert_memory_node = self._make_node(episode_id="episode-42")
        ctx = self._ctx_with_extraction()

        node.process(ctx)

        upsert_memory_node.upsert_facts.assert_called_once()
        kwargs = upsert_memory_node.upsert_facts.call_args.kwargs
        assert kwargs["peer_id"] == "client-acme"
        assert kwargs["facts"] == [{"fact": "Acme was quoted $150/hr."}]
        assert kwargs["evidence_episode_ids"] == ["episode-42"]

    def test_result_stored_with_episode_and_fact_ids(self):
        node, _, _ = self._make_node(episode_id="episode-1", upserted_ids=["fact-1", "fact-2"])
        ctx = self._ctx_with_extraction()

        node.process(ctx)

        stored = ctx.get_node_output("MemoryWriteNode")["result"]
        assert stored["episode_id"] == "episode-1"
        assert stored["peer_id"] == "client-acme"
        assert stored["upserted_fact_ids"] == ["fact-1", "fact-2"]

    def test_no_facts_still_writes_episode(self):
        node, episode_write_service, upsert_memory_node = self._make_node(upserted_ids=[])
        ctx = self._ctx_with_extraction(facts=[])

        node.process(ctx)

        episode_write_service.write.assert_called_once()
        upsert_memory_node.upsert_facts.assert_called_once_with(
            peer_id="client-acme", facts=[], evidence_episode_ids=["episode-1"]
        )
