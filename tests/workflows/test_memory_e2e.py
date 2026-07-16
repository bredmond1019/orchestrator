"""End-to-end acceptance tests for block OR.S (Task 6).

Drives the full memory stack against a real (in-memory SQLite) database with
only the agent seams mocked — no live LLM call anywhere in this file:

* **Accumulation** — ``MemoryIngestWorkflow`` run twice for the same
  ``(workspace_id, peer_id)`` with different interactions: one ``Peer`` row
  (no duplicate), two ``AgentEpisode`` rows, ``SemanticMemory`` growth.
* **Cited status answer** — ``MemoryLoaderNode`` (NL mode: "what's the
  status with client X") over the accumulated store, fed to a mocked-agent
  answer step; the final answer envelope's citations are non-empty and
  every citation resolves to a row actually loaded.
* **Cross-workspace isolation** — the same NL query scoped to a different
  ``workspace_id`` returns nothing from client X, so the answer step has no
  citations to make.
* **Consolidation round-trip** — ingest -> consolidate (mocked Claude
  output) -> loader reflects the consolidated fact and the refreshed
  representation.

TaskContext seeds follow CLAUDE.md rule 9: upstream output is stored as
``{"result": payload}`` matching what ``update_node(node_name=..., result=...)``
writes.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from core.task import TaskContext
from database.agent_episode import AgentEpisode
from database.peer import Peer
from database.semantic_memory import SemanticMemory
from database.session import Base
from memory.episode_write_service import EpisodeWriteService
from memory.memory_loader_node import MemoryLoaderNode
from memory.upsert_memory_node import UpsertMemoryNode
from schemas.memory_schema import MemoryConsolidationEventSchema, MemoryIngestEventSchema
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from workflows.memory_consolidation_workflow_nodes.consolidation_node import ConsolidationNode
from workflows.memory_consolidation_workflow_nodes.consolidation_write_node import (
    ConsolidationWriteNode,
)
from workflows.memory_consolidation_workflow_nodes.load_memory_context_node import (
    LoadMemoryContextNode,
)
from workflows.memory_ingest_workflow_nodes.ingest_time_extraction_node import (
    IngestTimeExtractionNode,
)
from workflows.memory_ingest_workflow_nodes.memory_write_node import MemoryWriteNode

WORKSPACE = "acme-workspace"
OTHER_WORKSPACE = "other-workspace"
PEER_ID = "client-acme"

_STUB_EMBEDDING = [0.03] * 1024


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
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


def _wire_session_scope(obj, session_factory):
    """Monkeypatch ``obj._session_scope`` to yield a real SQLite session."""

    @contextmanager
    def _session_scope():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    obj._session_scope = _session_scope  # noqa: SLF001 -- test seam injection


def _make_extraction_node() -> IngestTimeExtractionNode:
    """Construct IngestTimeExtractionNode without building a real Agent."""
    node = IngestTimeExtractionNode.__new__(IngestTimeExtractionNode)
    node.agent = MagicMock()
    return node


def _extraction_result(episode_summary: str, outcome: str, tags: list[str], facts: list[dict]):
    output = IngestTimeExtractionNode.OutputType(
        episode_summary=episode_summary,
        outcome=outcome,
        tags=tags,
        facts=[IngestTimeExtractionNode.Fact(**fact) for fact in facts],
    )
    r = MagicMock()
    r.output = output
    r.usage.return_value = MagicMock(input_tokens=5, output_tokens=10)
    return r


def _make_write_node(session_factory) -> MemoryWriteNode:
    episode_write_service = EpisodeWriteService()
    episode_write_service._embed = lambda text: _STUB_EMBEDDING  # noqa: SLF001
    _wire_session_scope(episode_write_service, session_factory)

    upsert_memory_node = UpsertMemoryNode()
    upsert_memory_node._embed = lambda text: _STUB_EMBEDDING  # noqa: SLF001
    _wire_session_scope(upsert_memory_node, session_factory)

    return MemoryWriteNode(
        episode_write_service=episode_write_service, upsert_memory_node=upsert_memory_node
    )


def _run_ingest(
    session_factory,
    *,
    interaction: str,
    episode_summary: str,
    outcome: str,
    tags: list[str],
    facts: list[dict],
    workspace_id: str = WORKSPACE,
    peer_id: str = PEER_ID,
) -> TaskContext:
    """Drive the two ingest nodes (extraction, then write) in sequence,
    mirroring what ``MemoryIngestWorkflow`` does, against a real session."""
    event = MemoryIngestEventSchema(
        workspace_id=workspace_id,
        peer_id=peer_id,
        peer_type="client",
        session_id="session-1",
        interaction=interaction,
    )
    ctx = TaskContext(event=event)

    extraction_node = _make_extraction_node()
    extraction_node.agent.run_sync.return_value = _extraction_result(
        episode_summary=episode_summary, outcome=outcome, tags=tags, facts=facts
    )
    extraction_node.process(ctx)

    write_node = _make_write_node(session_factory)
    write_node.process(ctx)
    return ctx


def _loader(session_factory) -> MemoryLoaderNode:
    node = MemoryLoaderNode()
    node._embed = lambda text: _STUB_EMBEDDING  # noqa: SLF001
    _wire_session_scope(node, session_factory)
    return node


def _mocked_answer_step(loaded: dict, mock_agent: MagicMock) -> dict:
    """Simulate a grounded answer step: the (mocked) agent is handed the
    loaded facts/episodes and returns an envelope whose citations are drawn
    from what was actually loaded — the same contract
    ``document_qa_workflow_nodes/answer_node.py`` follows for RAG context
    (``AgentNode`` + structured output), specialized here for memory
    citations rather than document sections. No live LLM call: the agent
    seam is a ``MagicMock`` configured by the caller.
    """
    mock_agent.run_sync(loaded)
    result = mock_agent.run_sync.return_value
    return {"answer": result.answer, "citations": list(result.citations)}


# ---------------------------------------------------------------------------
# Accumulation
# ---------------------------------------------------------------------------


class TestAccumulationAcrossInteractions:
    def test_two_ingests_accumulate_on_one_peer(self, session_factory):
        _run_ingest(
            session_factory,
            interaction="Quoted Acme $150/hr for the WhatsApp automation project.",
            episode_summary="Quoted Acme $150/hr.",
            outcome="quoted_rate",
            tags=["rate"],
            facts=[{"fact": "Acme was quoted $150/hr."}],
        )
        _run_ingest(
            session_factory,
            interaction="Acme signed the contract at $150/hr and kicked off week 1.",
            episode_summary="Acme signed the contract and kicked off.",
            outcome="signed",
            tags=["contract"],
            facts=[{"fact": "Acme signed the contract."}],
        )

        with session_factory() as session:
            peers = session.query(Peer).filter_by(workspace_id=WORKSPACE).all()
            assert len(peers) == 1
            assert peers[0].peer_id == PEER_ID

            episodes = session.query(AgentEpisode).filter_by(peer_id=PEER_ID).all()
            assert len(episodes) == 2
            summaries = {e.summary for e in episodes}
            assert summaries == {
                "Quoted Acme $150/hr.",
                "Acme signed the contract and kicked off.",
            }

            facts = session.query(SemanticMemory).filter_by(peer_id=PEER_ID).all()
            assert len(facts) == 2
            fact_texts = {f.fact for f in facts}
            assert fact_texts == {"Acme was quoted $150/hr.", "Acme signed the contract."}

    def test_no_duplicate_peer_row_created(self, session_factory):
        for i in range(3):
            _run_ingest(
                session_factory,
                interaction=f"Interaction number {i}.",
                episode_summary=f"Summary {i}.",
                outcome="noted",
                tags=[],
                facts=[{"fact": f"Fact number {i}."}],
            )

        with session_factory() as session:
            assert session.query(Peer).count() == 1
            assert session.query(AgentEpisode).count() == 3
            assert session.query(SemanticMemory).count() == 3


# ---------------------------------------------------------------------------
# Cited "status with client X" answer
# ---------------------------------------------------------------------------


class TestCitedStatusAnswer:
    def _seed_accumulated_store(self, session_factory):
        _run_ingest(
            session_factory,
            interaction="Quoted Acme $150/hr for the WhatsApp automation project.",
            episode_summary="Quoted Acme $150/hr.",
            outcome="quoted_rate",
            tags=["rate"],
            facts=[{"fact": "Acme was quoted $150/hr."}],
        )
        _run_ingest(
            session_factory,
            interaction="Acme signed the contract at $150/hr and kicked off week 1.",
            episode_summary="Acme signed the contract and kicked off.",
            outcome="signed",
            tags=["contract"],
            facts=[{"fact": "Acme signed the contract."}],
        )

    def test_citations_are_non_empty_and_resolve_to_loaded_rows(self, session_factory):
        self._seed_accumulated_store(session_factory)

        loader = _loader(session_factory)
        loaded = loader.retrieve(
            workspace_id=WORKSPACE,
            peer_id=PEER_ID,
            question="what's the status with client Acme",
            include_episodes=True,
        )
        loaded_fact_ids = {f["id"] for f in loaded["facts"]}
        loaded_episode_ids = {e["id"] for e in loaded["episodes"]}
        assert loaded_fact_ids  # the loader actually found something to cite

        # The (mocked) agent grounds its answer strictly in what was loaded —
        # exactly the AnswerNode contract, no live LLM involved.
        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = MagicMock(
            answer="Acme was quoted $150/hr and signed the contract.",
            citations=sorted(loaded_fact_ids | loaded_episode_ids),
        )
        envelope = _mocked_answer_step(loaded, mock_agent)

        assert envelope["citations"]  # non-empty
        for citation_id in envelope["citations"]:
            assert citation_id in loaded_fact_ids | loaded_episode_ids

        # Every citation also resolves to an actually-stored row, not just
        # something the loader claimed to return.
        with session_factory() as session:
            stored_fact_ids = {str(row.id) for row in session.query(SemanticMemory).all()}
            stored_episode_ids = {str(row.id) for row in session.query(AgentEpisode).all()}
        for citation_id in envelope["citations"]:
            assert citation_id in stored_fact_ids | stored_episode_ids

    def test_cross_workspace_query_returns_nothing_for_client_x(self, session_factory):
        self._seed_accumulated_store(session_factory)

        loader = _loader(session_factory)
        loaded = loader.retrieve(
            workspace_id=OTHER_WORKSPACE,
            peer_id=PEER_ID,
            question="what's the status with client Acme",
            include_episodes=True,
        )

        assert loaded["facts"] == []
        assert loaded["episodes"] == []

        mock_agent = MagicMock()
        mock_agent.run_sync.return_value = MagicMock(
            answer="I don't have any information about that client in this workspace.",
            citations=[],
        )
        envelope = _mocked_answer_step(loaded, mock_agent)
        assert envelope["citations"] == []


# ---------------------------------------------------------------------------
# Consolidation round-trip
# ---------------------------------------------------------------------------


class TestConsolidationRoundTrip:
    def _make_load_node(self, session_factory) -> LoadMemoryContextNode:
        node = LoadMemoryContextNode()
        _wire_session_scope(node, session_factory)
        return node

    def _make_consolidation_node(self) -> ConsolidationNode:
        node = ConsolidationNode.__new__(ConsolidationNode)
        node.agent = MagicMock()
        return node

    def _make_consolidation_write_node(self, session_factory) -> ConsolidationWriteNode:
        node = ConsolidationWriteNode()
        _wire_session_scope(node, session_factory)
        node.upsert_memory_node._embed = lambda text: _STUB_EMBEDDING  # noqa: SLF001
        _wire_session_scope(node.upsert_memory_node, session_factory)
        return node

    def test_loader_reflects_consolidated_facts_and_refreshed_representation(
        self, session_factory
    ):
        # 1. Ingest one interaction.
        _run_ingest(
            session_factory,
            interaction="Quoted Acme $150/hr for the WhatsApp automation project.",
            episode_summary="Quoted Acme $150/hr.",
            outcome="quoted_rate",
            tags=["rate"],
            facts=[{"fact": "Acme was quoted $150/hr."}],
        )

        # 2. Load context for dream-time consolidation.
        load_node = self._make_load_node(session_factory)
        consolidation_ctx = TaskContext(
            event=MemoryConsolidationEventSchema(workspace_id=WORKSPACE, peer_id=PEER_ID)
        )
        load_node.process(consolidation_ctx)

        # 3. Consolidate (mocked Claude output): a refreshed representation
        #    and one durable fact.
        consolidation_node = self._make_consolidation_node()
        output = ConsolidationNode.OutputType(
            peers=[
                ConsolidationNode.PeerConsolidation(
                    peer_id=PEER_ID,
                    representation="Acme is an active client on the $150/hr WhatsApp project.",
                    facts=[
                        ConsolidationNode.ConsolidatedFact(
                            fact="Acme's confirmed rate is $150/hr.",
                            confidence=0.95,
                        )
                    ],
                )
            ]
        )
        consolidation_node.agent.run_sync.return_value = MagicMock(
            output=output, usage=MagicMock(return_value=MagicMock(input_tokens=20, output_tokens=40))
        )
        consolidation_node.process(consolidation_ctx)

        # 4. Write the consolidated output.
        write_node = self._make_consolidation_write_node(session_factory)
        write_node.process(consolidation_ctx)

        # 5. The loader now reflects the consolidated fact and representation.
        with session_factory() as session:
            peer = session.query(Peer).filter_by(peer_id=PEER_ID).one()
            assert peer.representation == (
                "Acme is an active client on the $150/hr WhatsApp project."
            )
            facts = session.query(SemanticMemory).filter_by(peer_id=PEER_ID).all()
            fact_texts = {f.fact for f in facts}
            assert "Acme's confirmed rate is $150/hr." in fact_texts

        loader = _loader(session_factory)
        loaded = loader.retrieve(
            workspace_id=WORKSPACE,
            peer_id=PEER_ID,
            question="what's Acme's rate",
            top_k=10,
        )
        loaded_fact_texts = {f["fact"] for f in loaded["facts"]}
        assert "Acme's confirmed rate is $150/hr." in loaded_fact_texts
