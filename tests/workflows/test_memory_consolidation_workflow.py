"""Tests for MemoryConsolidationWorkflow (block OR.S, Task 4).

Four layers:

* **Structure** — registration in ``WorkflowRegistry`` + ``SCHEMA_MAP``
  (CLAUDE.md standing rule 6), schema wiring (start node, linear three-node
  connections), ``WorkflowValidator`` acceptance.
* **Event schema** — ``MemoryConsolidationEventSchema`` validates the
  required/optional fields (``peer_id``/``since`` optional).
* **D35 guard** — ``ConsolidationNode.get_agent_config()`` is pinned to a
  Claude-family provider; a config drift to a local model must fail this
  test.
* **Nodes** — ``LoadMemoryContextNode`` and ``ConsolidationWriteNode``
  against a real in-memory SQLite session (mirroring
  ``tests/memory/test_episode_write_service.py``), ``ConsolidationNode``
  with the agent seam mocked (no live LLM call), proving: consolidation
  output schema validity for the multi-peer case with per-peer isolation,
  and contradiction resolution routed through the never-overwrite rule.

TaskContext seeds follow CLAUDE.md rule 9: upstream output is stored as
``{"result": payload}`` matching what ``update_node(node_name=..., result=...)``
writes.
"""

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from core.nodes.agent import ModelProvider
from core.task import TaskContext
from core.validate import WorkflowValidator
from database.agent_episode import AgentEpisode
from database.peer import Peer, PeerType
from database.semantic_memory import SemanticMemory
from database.session import Base
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from schemas.memory_schema import MemoryConsolidationEventSchema
from workflows.memory_consolidation_workflow import MemoryConsolidationWorkflow
from workflows.memory_consolidation_workflow_nodes.consolidation_node import ConsolidationNode
from workflows.memory_consolidation_workflow_nodes.consolidation_write_node import (
    ConsolidationWriteNode,
)
from workflows.memory_consolidation_workflow_nodes.load_memory_context_node import (
    LoadMemoryContextNode,
)

_STUB_EMBEDDING = [0.03] * 1024


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


class TestMemoryConsolidationWorkflowStructure:
    def test_start_is_load_memory_context_node(self):
        assert MemoryConsolidationWorkflow.workflow_schema.start is LoadMemoryContextNode

    def test_event_schema_is_memory_consolidation(self):
        assert (
            MemoryConsolidationWorkflow.workflow_schema.event_schema
            is MemoryConsolidationEventSchema
        )

    def test_three_nodes_in_workflow(self):
        node_classes = {
            nc.node for nc in MemoryConsolidationWorkflow.workflow_schema.nodes
        }
        assert node_classes == {
            LoadMemoryContextNode,
            ConsolidationNode,
            ConsolidationWriteNode,
        }

    def test_linear_dag_connections(self):
        node_map = {
            nc.node: nc.connections
            for nc in MemoryConsolidationWorkflow.workflow_schema.nodes
        }
        assert node_map[LoadMemoryContextNode] == [ConsolidationNode]
        assert node_map[ConsolidationNode] == [ConsolidationWriteNode]
        assert node_map[ConsolidationWriteNode] == []

    def test_no_routers(self):
        for nc in MemoryConsolidationWorkflow.workflow_schema.nodes:
            assert not nc.is_router

    def test_workflow_validator_accepts_schema(self):
        validator = WorkflowValidator(MemoryConsolidationWorkflow.workflow_schema)
        validator.validate()  # must not raise


class TestWorkflowRegistryCompleteness:
    """CLAUDE.md standing rule 6: registered in BOTH registries."""

    def test_memory_consolidation_registered_in_workflow_registry(self):
        from workflows.workflow_registry import WorkflowRegistry

        assert (
            WorkflowRegistry.MEMORY_CONSOLIDATION.value is MemoryConsolidationWorkflow
        )

    def test_memory_consolidation_registered_in_schema_map(self):
        from api.schema_registry import SCHEMA_MAP
        from workflows.workflow_registry import WorkflowRegistry

        assert (
            SCHEMA_MAP[WorkflowRegistry.MEMORY_CONSOLIDATION.name]
            is MemoryConsolidationEventSchema
        )

    def test_every_workflow_has_schema_map_entry(self):
        """Guards against reintroducing the missing-registration bug for any workflow."""
        from api.schema_registry import SCHEMA_MAP
        from workflows.workflow_registry import WorkflowRegistry

        missing = [
            member.name for member in WorkflowRegistry if member.name not in SCHEMA_MAP
        ]
        assert not missing


# ---------------------------------------------------------------------------
# Event schema
# ---------------------------------------------------------------------------


class TestMemoryConsolidationEventSchema:
    def test_valid_event_peer_and_since(self):
        event = MemoryConsolidationEventSchema(
            workspace_id="acme-workspace",
            peer_id="client-acme",
            since=datetime(2026, 1, 1),
        )
        assert event.workspace_id == "acme-workspace"
        assert event.peer_id == "client-acme"
        assert event.since == datetime(2026, 1, 1)

    def test_peer_id_optional_defaults_to_none(self):
        event = MemoryConsolidationEventSchema(workspace_id="acme-workspace")
        assert event.peer_id is None

    def test_since_optional_defaults_to_none(self):
        event = MemoryConsolidationEventSchema(workspace_id="acme-workspace")
        assert event.since is None

    def test_missing_workspace_id_raises(self):
        with pytest.raises(ValidationError):
            MemoryConsolidationEventSchema()


# ---------------------------------------------------------------------------
# D35 guard — Claude-only consolidation
# ---------------------------------------------------------------------------


class TestD35ProviderGuard:
    """Dream-time consolidation must stay on Claude, never a local model."""

    def test_agent_config_uses_claude_provider(self):
        node = ConsolidationNode.__new__(ConsolidationNode)
        config = node.get_agent_config()
        assert config.model_provider in (
            ModelProvider.CLAUDE_CODE_SDK,
            ModelProvider.CLAUDE_CODE_SESSION,
            ModelProvider.ANTHROPIC,
        )

    def test_agent_config_is_not_a_local_or_non_claude_provider(self):
        node = ConsolidationNode.__new__(ConsolidationNode)
        config = node.get_agent_config()
        assert config.model_provider not in (
            ModelProvider.OLLAMA,
            ModelProvider.OPENAI,
            ModelProvider.AZURE_OPENAI,
            ModelProvider.GEMINI,
            ModelProvider.BEDROCK,
        )


# ---------------------------------------------------------------------------
# LoadMemoryContextNode — real in-memory SQLite session
# ---------------------------------------------------------------------------


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Peer.__table__, AgentEpisode.__table__, SemanticMemory.__table__],
    )
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def _seed_peer(session_factory, **overrides) -> Peer:
    defaults = dict(
        peer_id="client-acme",
        peer_type=PeerType.CLIENT,
        workspace_id="acme-workspace",
        representation="Acme is a mid-market retailer.",
    )
    defaults.update(overrides)
    with session_factory() as session:
        peer = Peer(**defaults)
        session.add(peer)
        session.commit()
        session.expunge(peer)
        return peer


def _seed_episode(session_factory, **overrides) -> AgentEpisode:
    defaults = dict(
        peer_id="client-acme",
        summary="Quoted Acme $150/hr.",
        outcome="quoted_rate",
        tags=["rate"],
        embedding=_STUB_EMBEDDING,
        occurred_at=datetime(2026, 1, 1),
    )
    defaults.update(overrides)
    with session_factory() as session:
        episode = AgentEpisode(**defaults)
        session.add(episode)
        session.commit()
        session.expunge(episode)
        return episode


def _seed_fact(session_factory, **overrides) -> SemanticMemory:
    defaults = dict(
        peer_id="client-acme",
        fact="Acme was quoted $150/hr.",
        confidence=0.9,
        evidence_episode_ids=[],
        embedding=_STUB_EMBEDDING,
    )
    defaults.update(overrides)
    with session_factory() as session:
        row = SemanticMemory(**defaults)
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def _load_node(session_factory) -> LoadMemoryContextNode:
    node = LoadMemoryContextNode()

    @contextmanager
    def _session_scope():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    node._session_scope = _session_scope  # noqa: SLF001 -- test seam injection
    return node


def _ctx(event: MemoryConsolidationEventSchema) -> TaskContext:
    return TaskContext(event=event)


class TestLoadMemoryContextNode:
    def test_single_peer_loads_episodes_facts_and_representation(self, session_factory):
        _seed_peer(session_factory)
        _seed_episode(session_factory)
        _seed_fact(session_factory)
        node = _load_node(session_factory)

        ctx = _ctx(
            MemoryConsolidationEventSchema(
                workspace_id="acme-workspace", peer_id="client-acme"
            )
        )
        node.process(ctx)

        result = ctx.get_node_output("LoadMemoryContextNode")["result"]
        assert result["workspace_id"] == "acme-workspace"
        assert len(result["peers"]) == 1
        peer_ctx = result["peers"][0]
        assert peer_ctx["peer_id"] == "client-acme"
        assert peer_ctx["representation"] == "Acme is a mid-market retailer."
        assert len(peer_ctx["episodes"]) == 1
        assert peer_ctx["episodes"][0]["summary"] == "Quoted Acme $150/hr."
        assert len(peer_ctx["facts"]) == 1
        assert peer_ctx["facts"][0]["fact"] == "Acme was quoted $150/hr."

    def test_omitted_peer_id_loads_every_peer_in_workspace(self, session_factory):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_peer(session_factory, peer_id="client-beta")
        node = _load_node(session_factory)

        ctx = _ctx(MemoryConsolidationEventSchema(workspace_id="acme-workspace"))
        node.process(ctx)

        result = ctx.get_node_output("LoadMemoryContextNode")["result"]
        peer_ids = {p["peer_id"] for p in result["peers"]}
        assert peer_ids == {"client-acme", "client-beta"}

    def test_workspace_isolation_never_loads_another_workspaces_peer(
        self, session_factory
    ):
        _seed_peer(session_factory, peer_id="client-acme", workspace_id="workspace-x")
        _seed_peer(session_factory, peer_id="client-beta", workspace_id="workspace-y")
        node = _load_node(session_factory)

        ctx = _ctx(MemoryConsolidationEventSchema(workspace_id="workspace-x"))
        node.process(ctx)

        result = ctx.get_node_output("LoadMemoryContextNode")["result"]
        peer_ids = {p["peer_id"] for p in result["peers"]}
        assert peer_ids == {"client-acme"}

    def test_since_filters_out_older_episodes(self, session_factory):
        _seed_peer(session_factory)
        _seed_episode(
            session_factory, summary="Old interaction.", occurred_at=datetime(2025, 1, 1)
        )
        _seed_episode(
            session_factory, summary="Recent interaction.", occurred_at=datetime(2026, 6, 1)
        )
        node = _load_node(session_factory)

        ctx = _ctx(
            MemoryConsolidationEventSchema(
                workspace_id="acme-workspace",
                peer_id="client-acme",
                since=datetime(2026, 1, 1),
            )
        )
        node.process(ctx)

        result = ctx.get_node_output("LoadMemoryContextNode")["result"]
        summaries = [e["summary"] for e in result["peers"][0]["episodes"]]
        assert summaries == ["Recent interaction."]

    def test_no_matching_peer_returns_empty_peers_list(self, session_factory):
        node = _load_node(session_factory)

        ctx = _ctx(
            MemoryConsolidationEventSchema(
                workspace_id="acme-workspace", peer_id="does-not-exist"
            )
        )
        node.process(ctx)

        result = ctx.get_node_output("LoadMemoryContextNode")["result"]
        assert result["peers"] == []


# ---------------------------------------------------------------------------
# ConsolidationNode — agent seam mocked
# ---------------------------------------------------------------------------


def _make_consolidation_node() -> ConsolidationNode:
    """Construct ConsolidationNode without building a real Agent."""
    node = ConsolidationNode.__new__(ConsolidationNode)
    node.agent = MagicMock()
    return node


def _consolidation_result(peers: list[dict]):
    output = ConsolidationNode.OutputType(
        peers=[
            ConsolidationNode.PeerConsolidation(
                peer_id=peer["peer_id"],
                representation=peer["representation"],
                facts=[
                    ConsolidationNode.ConsolidatedFact(**fact)
                    for fact in peer.get("facts", [])
                ],
            )
            for peer in peers
        ]
    )
    r = MagicMock()
    r.output = output
    r.usage.return_value = MagicMock(input_tokens=20, output_tokens=40)
    return r


class TestConsolidationNode:
    def test_result_stored_under_result_key(self):
        node = _make_consolidation_node()
        node.agent.run_sync.return_value = _consolidation_result(
            [{"peer_id": "client-acme", "representation": "Acme summary.", "facts": []}]
        )

        ctx = TaskContext(event=MemoryConsolidationEventSchema(workspace_id="acme-workspace"))
        ctx.nodes["LoadMemoryContextNode"] = {
            "result": {
                "workspace_id": "acme-workspace",
                "peers": [
                    {
                        "peer_id": "client-acme",
                        "peer_type": "client",
                        "representation": "Old summary.",
                        "episodes": [],
                        "facts": [],
                    }
                ],
            }
        }

        node.process(ctx)

        assert "result" in ctx.nodes["ConsolidationNode"]

    def test_multi_peer_output_stays_isolated_per_peer(self):
        """Consolidation output schema validity for the multi-peer case: each
        peer's facts appear only under its own peer_id, never bleeding into
        another peer's entry."""
        node = _make_consolidation_node()
        node.agent.run_sync.return_value = _consolidation_result(
            [
                {
                    "peer_id": "client-acme",
                    "representation": "Acme summary.",
                    "facts": [{"fact": "Acme fact A."}],
                },
                {
                    "peer_id": "client-beta",
                    "representation": "Beta summary.",
                    "facts": [{"fact": "Beta fact A."}],
                },
            ]
        )

        ctx = TaskContext(event=MemoryConsolidationEventSchema(workspace_id="acme-workspace"))
        ctx.nodes["LoadMemoryContextNode"] = {
            "result": {
                "workspace_id": "acme-workspace",
                "peers": [
                    {
                        "peer_id": "client-acme",
                        "peer_type": "client",
                        "representation": "",
                        "episodes": [],
                        "facts": [],
                    },
                    {
                        "peer_id": "client-beta",
                        "peer_type": "client",
                        "representation": "",
                        "episodes": [],
                        "facts": [],
                    },
                ],
            }
        }

        node.process(ctx)

        stored = ctx.get_node_output("ConsolidationNode")["result"]
        by_peer = {peer["peer_id"]: peer for peer in stored["peers"]}
        assert set(by_peer) == {"client-acme", "client-beta"}
        assert by_peer["client-acme"]["facts"] == [
            {
                "fact": "Acme fact A.",
                "confidence": None,
                "contradicts_fact_id": None,
                "evidence_episode_ids": [],
            }
        ]
        assert by_peer["client-beta"]["facts"] == [
            {
                "fact": "Beta fact A.",
                "confidence": None,
                "contradicts_fact_id": None,
                "evidence_episode_ids": [],
            }
        ]

    def test_workspace_id_passed_through(self):
        node = _make_consolidation_node()
        node.agent.run_sync.return_value = _consolidation_result([])

        ctx = TaskContext(event=MemoryConsolidationEventSchema(workspace_id="acme-workspace"))
        ctx.nodes["LoadMemoryContextNode"] = {
            "result": {"workspace_id": "acme-workspace", "peers": []}
        }

        node.process(ctx)

        stored = ctx.get_node_output("ConsolidationNode")["result"]
        assert stored["workspace_id"] == "acme-workspace"


# ---------------------------------------------------------------------------
# ConsolidationWriteNode — real in-memory SQLite session
# ---------------------------------------------------------------------------


def _write_node(session_factory, **kwargs) -> ConsolidationWriteNode:
    node = ConsolidationWriteNode(**kwargs)

    @contextmanager
    def _session_scope():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    node._session_scope = _session_scope  # noqa: SLF001 -- test seam injection
    node.upsert_memory_node._session_scope = _session_scope  # noqa: SLF001
    node.upsert_memory_node._embed = lambda text: _STUB_EMBEDDING  # noqa: SLF001
    return node


def _ctx_with_consolidation(peers: list[dict]) -> TaskContext:
    ctx = TaskContext(event=MemoryConsolidationEventSchema(workspace_id="acme-workspace"))
    ctx.nodes["ConsolidationNode"] = {
        "result": {"workspace_id": "acme-workspace", "peers": peers}
    }
    return ctx


class TestConsolidationWriteNode:
    def test_writes_new_fact_and_refreshes_representation(self, session_factory):
        _seed_peer(session_factory, representation="Old summary.")
        node = _write_node(session_factory)

        ctx = _ctx_with_consolidation(
            [
                {
                    "peer_id": "client-acme",
                    "representation": "New, refreshed summary.",
                    "facts": [{"fact": "A new durable fact."}],
                }
            ]
        )
        node.process(ctx)

        with session_factory() as session:
            peer = session.query(Peer).filter_by(peer_id="client-acme").one()
            assert peer.representation == "New, refreshed summary."
            assert session.query(SemanticMemory).count() == 1
            assert (
                session.query(SemanticMemory).first().fact == "A new durable fact."
            )

    def test_contradiction_lowers_old_confidence_and_adds_new_row(
        self, session_factory
    ):
        """Contradiction resolution routed through the never-overwrite rule."""
        _seed_peer(session_factory)
        original = _seed_fact(session_factory, confidence=0.9)
        node = _write_node(session_factory)

        ctx = _ctx_with_consolidation(
            [
                {
                    "peer_id": "client-acme",
                    "representation": "Rate was renegotiated.",
                    "facts": [
                        {
                            "fact": "Acme's rate was renegotiated to $175/hr.",
                            "confidence": 0.9,
                            "contradicts_fact_id": str(original.id),
                        }
                    ],
                }
            ]
        )
        node.process(ctx)

        with session_factory() as session:
            assert session.query(SemanticMemory).count() == 2
            preserved = session.query(SemanticMemory).filter_by(id=original.id).one()
            assert preserved.confidence < 0.9
            assert preserved.fact == original.fact
            new_row = (
                session.query(SemanticMemory)
                .filter(SemanticMemory.id != original.id)
                .one()
            )
            assert new_row.fact == "Acme's rate was renegotiated to $175/hr."

    def test_multi_peer_writes_stay_isolated(self, session_factory):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_peer(session_factory, peer_id="client-beta")
        node = _write_node(session_factory)

        ctx = _ctx_with_consolidation(
            [
                {
                    "peer_id": "client-acme",
                    "representation": "Acme summary.",
                    "facts": [{"fact": "Acme-only fact."}],
                },
                {
                    "peer_id": "client-beta",
                    "representation": "Beta summary.",
                    "facts": [{"fact": "Beta-only fact."}],
                },
            ]
        )
        node.process(ctx)

        with session_factory() as session:
            acme_facts = session.query(SemanticMemory).filter_by(peer_id="client-acme").all()
            beta_facts = session.query(SemanticMemory).filter_by(peer_id="client-beta").all()
            assert [f.fact for f in acme_facts] == ["Acme-only fact."]
            assert [f.fact for f in beta_facts] == ["Beta-only fact."]

    def test_unknown_peer_id_does_not_raise(self, session_factory):
        node = _write_node(session_factory)
        ctx = _ctx_with_consolidation(
            [
                {
                    "peer_id": "does-not-exist",
                    "representation": "Some summary.",
                    "facts": [],
                }
            ]
        )
        node.process(ctx)  # must not raise

        stored = ctx.get_node_output("ConsolidationWriteNode")["result"]
        assert stored["peers"][0]["peer_id"] == "does-not-exist"

    def test_result_stored_with_upserted_fact_ids(self, session_factory):
        _seed_peer(session_factory)
        node = _write_node(session_factory)

        ctx = _ctx_with_consolidation(
            [
                {
                    "peer_id": "client-acme",
                    "representation": "Summary.",
                    "facts": [{"fact": "Fact one."}, {"fact": "Fact two."}],
                }
            ]
        )
        node.process(ctx)

        stored = ctx.get_node_output("ConsolidationWriteNode")["result"]
        assert stored["workspace_id"] == "acme-workspace"
        assert len(stored["peers"][0]["upserted_fact_ids"]) == 2
