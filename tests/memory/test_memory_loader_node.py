"""Tests for app/memory/memory_loader_node.py — MemoryLoaderNode.

Covers the two query modes (cosine, NL-question), decay-weighted ranking in
NL-question mode, multi-peer + multi-workspace isolation, top_k respected,
and the context-budget warning guard. Also covers ``process()`` reading
loader params off ``task_context.event`` per design decision 1 (no coupling
to a specific upstream node).

DB access goes through an in-memory SQLite session injected via the
``_session_scope`` seam; ``_embed`` is stubbed to avoid a live embedding
provider call.
"""

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from core.task import TaskContext
from database.agent_episode import AgentEpisode
from database.peer import Peer, PeerType
from database.semantic_memory import SemanticMemory
from database.session import Base
from freezegun import freeze_time
from memory.memory_loader_node import (
    DEFAULT_BUDGET_RATIO,
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    MemoryLoaderNode,
    _cosine_similarity,
    _estimate_tokens,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

WORKSPACE = "agentic-portfolio"
OTHER_WORKSPACE = "other-workspace"


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


@pytest.fixture
def node(session_factory):
    n = MemoryLoaderNode(top_k=5)

    @contextmanager
    def _session_scope():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    n._session_scope = _session_scope  # noqa: SLF001 -- test seam injection
    return n


def _seed_peer(session_factory, *, peer_id: str, workspace_id: str = WORKSPACE) -> Peer:
    with session_factory() as session:
        peer = Peer(peer_id=peer_id, peer_type=PeerType.CLIENT, workspace_id=workspace_id)
        session.add(peer)
        session.commit()
        session.refresh(peer)
        session.expunge(peer)
        return peer


def _seed_fact(session_factory, *, peer_id: str, **overrides) -> SemanticMemory:
    defaults = dict(
        peer_id=peer_id,
        fact="A fact.",
        confidence=0.9,
        decay_factor=0.95,
        evidence_episode_ids=[],
        embedding=[1.0] + [0.0] * 1023,
    )
    defaults.update(overrides)
    with session_factory() as session:
        row = SemanticMemory(**defaults)
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def _seed_episode(session_factory, *, peer_id: str, **overrides) -> AgentEpisode:
    defaults = dict(
        peer_id=peer_id,
        summary="An episode summary.",
        outcome=None,
        tags=[],
        embedding=[1.0] + [0.0] * 1023,
        occurred_at=datetime(2026, 1, 1),
    )
    defaults.update(overrides)
    with session_factory() as session:
        row = AgentEpisode(**defaults)
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors_similarity_one(self):
        v = [1.0, 0.0, 0.0]
        assert _cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_similarity_zero(self):
        assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_similarity_negative_one(self):
        assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_empty_vector_returns_zero(self):
        assert _cosine_similarity([], [1.0]) == 0.0

    def test_zero_magnitude_vector_returns_zero(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


class TestEstimateTokens:
    def test_empty_text_zero_tokens(self):
        assert _estimate_tokens("") == 0

    def test_nonempty_text_at_least_one_token(self):
        assert _estimate_tokens("hi") >= 1

    def test_roughly_four_chars_per_token(self):
        assert _estimate_tokens("a" * 400) == 100


# ---------------------------------------------------------------------------
# Cosine mode
# ---------------------------------------------------------------------------


class TestCosineModeRetrieval:
    def test_ranks_by_similarity_descending(self, node, session_factory):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="Close match.",
            embedding=[1.0, 0.0] + [0.0] * 1022,
        )
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="Far match.",
            embedding=[0.0, 1.0] + [0.0] * 1022,
        )

        result = node.retrieve(
            workspace_id=WORKSPACE,
            peer_id="client-acme",
            query_embedding=[1.0, 0.0] + [0.0] * 1022,
        )

        facts = result["facts"]
        assert [f["fact"] for f in facts] == ["Close match.", "Far match."]
        assert facts[0]["score"] > facts[1]["score"]

    def test_score_ignores_confidence_in_cosine_mode(self, node, session_factory):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="Low confidence but identical vector.",
            confidence=0.1,
            embedding=[1.0] + [0.0] * 1023,
        )

        result = node.retrieve(
            workspace_id=WORKSPACE,
            peer_id="client-acme",
            query_embedding=[1.0] + [0.0] * 1023,
        )
        assert result["facts"][0]["score"] == pytest.approx(1.0)

    def test_top_k_respected(self, node, session_factory):
        _seed_peer(session_factory, peer_id="client-acme")
        for i in range(10):
            _seed_fact(
                session_factory,
                peer_id="client-acme",
                fact=f"Fact {i}.",
                embedding=[1.0] + [0.0] * 1023,
            )
        result = node.retrieve(
            workspace_id=WORKSPACE,
            peer_id="client-acme",
            query_embedding=[1.0] + [0.0] * 1023,
            top_k=3,
        )
        assert len(result["facts"]) == 3

    def test_requires_exactly_one_mode(self, node):
        with pytest.raises(ValueError):
            node.retrieve(workspace_id=WORKSPACE)
        with pytest.raises(ValueError):
            node.retrieve(
                workspace_id=WORKSPACE,
                query_embedding=[1.0],
                question="both supplied",
            )


# ---------------------------------------------------------------------------
# NL-question mode
# ---------------------------------------------------------------------------


class TestNLQuestionModeRetrieval:
    def test_embeds_question_and_ranks_by_similarity_times_confidence(
        self, node, session_factory, monkeypatch
    ):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="High confidence, exact match.",
            confidence=0.9,
            embedding=[1.0] + [0.0] * 1023,
        )
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="Low confidence, exact match.",
            confidence=0.1,
            embedding=[1.0] + [0.0] * 1023,
        )

        node._embed = lambda text: [1.0] + [0.0] * 1023  # noqa: SLF001

        result = node.retrieve(
            workspace_id=WORKSPACE,
            peer_id="client-acme",
            question="what's the status with client X",
        )

        facts = result["facts"]
        assert facts[0]["fact"] == "High confidence, exact match."
        assert facts[0]["score"] > facts[1]["score"]

    def test_decayed_confidence_affects_ranking(self, node, session_factory):
        updated_at = datetime(2026, 1, 1)
        _seed_peer(session_factory, peer_id="client-acme")
        # Same starting confidence and identical similarity to the query;
        # only decay elapsed differs.
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="Fresh fact.",
            confidence=0.9,
            decay_factor=0.95,
            embedding=[1.0] + [0.0] * 1023,
            updated_at=updated_at,
        )
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="Stale fact.",
            confidence=0.9,
            decay_factor=0.5,
            embedding=[1.0] + [0.0] * 1023,
            updated_at=updated_at,
        )

        node._embed = lambda text: [1.0] + [0.0] * 1023  # noqa: SLF001

        with freeze_time(updated_at + timedelta(weeks=4)):
            result = node.retrieve(
                workspace_id=WORKSPACE,
                peer_id="client-acme",
                question="status?",
            )

        facts = result["facts"]
        assert facts[0]["fact"] == "Fresh fact."
        assert facts[0]["effective_confidence"] > facts[1]["effective_confidence"]
        assert facts[0]["score"] > facts[1]["score"]

    def test_citations_carry_evidence_episode_ids(self, node, session_factory):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="Quoted $150/hr.",
            evidence_episode_ids=["episode-1", "episode-2"],
            embedding=[1.0] + [0.0] * 1023,
        )
        node._embed = lambda text: [1.0] + [0.0] * 1023  # noqa: SLF001

        result = node.retrieve(
            workspace_id=WORKSPACE, peer_id="client-acme", question="rate?"
        )
        assert result["facts"][0]["evidence_episode_ids"] == ["episode-1", "episode-2"]


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


class TestIsolation:
    def test_multi_peer_isolation(self, node, session_factory):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_peer(session_factory, peer_id="client-beta")
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="Acme fact.",
            embedding=[1.0] + [0.0] * 1023,
        )
        _seed_fact(
            session_factory,
            peer_id="client-beta",
            fact="Beta fact.",
            embedding=[1.0] + [0.0] * 1023,
        )

        result = node.retrieve(
            workspace_id=WORKSPACE,
            peer_id="client-acme",
            query_embedding=[1.0] + [0.0] * 1023,
        )
        assert [f["fact"] for f in result["facts"]] == ["Acme fact."]

    def test_workspace_isolation(self, node, session_factory):
        _seed_peer(session_factory, peer_id="client-acme", workspace_id=WORKSPACE)
        _seed_peer(session_factory, peer_id="client-acme-other", workspace_id=OTHER_WORKSPACE)
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="In-workspace fact.",
            embedding=[1.0] + [0.0] * 1023,
        )
        _seed_fact(
            session_factory,
            peer_id="client-acme-other",
            fact="Other-workspace fact.",
            embedding=[1.0] + [0.0] * 1023,
        )

        result = node.retrieve(
            workspace_id=WORKSPACE, query_embedding=[1.0] + [0.0] * 1023
        )
        assert [f["fact"] for f in result["facts"]] == ["In-workspace fact."]

    def test_no_peer_id_scopes_to_whole_workspace(self, node, session_factory):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_peer(session_factory, peer_id="client-beta")
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="Acme fact.",
            embedding=[1.0] + [0.0] * 1023,
        )
        _seed_fact(
            session_factory,
            peer_id="client-beta",
            fact="Beta fact.",
            embedding=[1.0] + [0.0] * 1023,
        )

        result = node.retrieve(
            workspace_id=WORKSPACE, query_embedding=[1.0] + [0.0] * 1023
        )
        assert {f["fact"] for f in result["facts"]} == {"Acme fact.", "Beta fact."}


# ---------------------------------------------------------------------------
# Episodes
# ---------------------------------------------------------------------------


class TestIncludeEpisodes:
    def test_include_episodes_returns_recent_summaries_ordered(
        self, node, session_factory
    ):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_episode(
            session_factory,
            peer_id="client-acme",
            summary="Older episode.",
            occurred_at=datetime(2026, 1, 1),
        )
        _seed_episode(
            session_factory,
            peer_id="client-acme",
            summary="Newer episode.",
            occurred_at=datetime(2026, 2, 1),
        )

        result = node.retrieve(
            workspace_id=WORKSPACE,
            peer_id="client-acme",
            query_embedding=[1.0] + [0.0] * 1023,
            include_episodes=True,
        )
        assert [e["summary"] for e in result["episodes"]] == [
            "Newer episode.",
            "Older episode.",
        ]

    def test_episodes_omitted_by_default(self, node, session_factory):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_episode(session_factory, peer_id="client-acme")

        result = node.retrieve(
            workspace_id=WORKSPACE,
            peer_id="client-acme",
            query_embedding=[1.0] + [0.0] * 1023,
        )
        assert result["episodes"] == []


# ---------------------------------------------------------------------------
# Context budget guard
# ---------------------------------------------------------------------------


class TestContextBudgetGuard:
    def test_warns_when_budget_exceeded(self, session_factory, caplog):
        n = MemoryLoaderNode(
            top_k=5, context_window_tokens=100, budget_ratio=DEFAULT_BUDGET_RATIO
        )

        @contextmanager
        def _session_scope():
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

        n._session_scope = _session_scope  # noqa: SLF001

        _seed_peer(session_factory, peer_id="client-acme")
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="x" * 2000,
            embedding=[1.0] + [0.0] * 1023,
        )

        with caplog.at_level(logging.WARNING, logger="memory.memory_loader_node"):
            n.retrieve(
                workspace_id=WORKSPACE,
                peer_id="client-acme",
                query_embedding=[1.0] + [0.0] * 1023,
            )
        assert any("context-injection budget" in r.message for r in caplog.records)

    def test_no_warning_when_within_budget(self, node, session_factory, caplog):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="Short fact.",
            embedding=[1.0] + [0.0] * 1023,
        )

        with caplog.at_level(logging.WARNING, logger="memory.memory_loader_node"):
            node.retrieve(
                workspace_id=WORKSPACE,
                peer_id="client-acme",
                query_embedding=[1.0] + [0.0] * 1023,
            )
        assert not any("context-injection budget" in r.message for r in caplog.records)

    def test_default_context_window_is_positive(self):
        assert DEFAULT_CONTEXT_WINDOW_TOKENS > 0


# ---------------------------------------------------------------------------
# process() / TaskContext integration
# ---------------------------------------------------------------------------


class TestProcess:
    def test_process_reads_params_from_event_and_writes_result(
        self, node, session_factory
    ):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="Event-driven fact.",
            embedding=[1.0] + [0.0] * 1023,
        )

        event = SimpleNamespace(
            workspace_id=WORKSPACE,
            peer_id="client-acme",
            query_embedding=[1.0] + [0.0] * 1023,
            top_k=None,
            include_episodes=False,
            episode_limit=None,
        )
        task_context = TaskContext(event=event)

        result_context = node.process(task_context)

        output = result_context.get_node_output("MemoryLoaderNode")["result"]
        assert output["facts"][0]["fact"] == "Event-driven fact."

    def test_process_nl_question_mode(self, node, session_factory):
        _seed_peer(session_factory, peer_id="client-acme")
        _seed_fact(
            session_factory,
            peer_id="client-acme",
            fact="NL-mode fact.",
            embedding=[1.0] + [0.0] * 1023,
        )
        node._embed = lambda text: [1.0] + [0.0] * 1023  # noqa: SLF001

        event = SimpleNamespace(
            workspace_id=WORKSPACE,
            peer_id="client-acme",
            question="what's the status with client X",
        )
        task_context = TaskContext(event=event)

        result_context = node.process(task_context)

        output = result_context.get_node_output("MemoryLoaderNode")["result"]
        assert output["facts"][0]["fact"] == "NL-mode fact."

    def test_process_missing_workspace_id_returns_empty_envelope(self, node):
        """Event has no ``workspace_id`` attribute at all (e.g. a schema that
        predates the D47 field) — must degrade gracefully, not raise
        ``AttributeError``, and must never enter the DB seam."""
        session_scope_called = False
        original_session_scope = node._session_scope  # noqa: SLF001

        @contextmanager
        def _tracking_session_scope():
            nonlocal session_scope_called
            session_scope_called = True
            with original_session_scope() as session:
                yield session

        node._session_scope = _tracking_session_scope  # noqa: SLF001

        event = SimpleNamespace()  # no workspace_id attribute at all
        task_context = TaskContext(event=event)

        result_context = node.process(task_context)

        output = result_context.get_node_output("MemoryLoaderNode")["result"]
        assert output == {"facts": [], "episodes": []}
        assert session_scope_called is False

    def test_process_none_workspace_id_returns_empty_envelope(self, node):
        """Event explicitly carries ``workspace_id=None`` — same graceful
        degradation as the attribute being absent entirely."""
        event = SimpleNamespace(workspace_id=None)
        task_context = TaskContext(event=event)

        result_context = node.process(task_context)

        output = result_context.get_node_output("MemoryLoaderNode")["result"]
        assert output == {"facts": [], "episodes": []}
