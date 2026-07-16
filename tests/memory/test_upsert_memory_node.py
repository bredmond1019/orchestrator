"""Tests for app/memory/upsert_memory_node.py — UpsertMemoryNode.

Covers the contradiction rule (never overwrite: old row's confidence drops,
a new row is created, the old row's fact text and id are untouched),
non-contradicting inserts, and decay being applied during the contradiction
comparison. Also covers ``process()`` reading from ``TaskContext`` per
CLAUDE.md standing rule 9 (upstream node output seeded as
``{"result": ...}``).

DB access goes through an in-memory SQLite session injected via the
``_session_scope`` seam; ``_embed`` is stubbed to avoid a live embedding
provider call.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from core.task import TaskContext
from database.semantic_memory import SemanticMemory
from database.session import Base
from freezegun import freeze_time
from memory.decay import effective_confidence
from memory.upsert_memory_node import CONTRADICTION_PENALTY, UpsertMemoryNode
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_STUB_EMBEDDING = [0.02] * 1024


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[SemanticMemory.__table__])
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture
def node(session_factory):
    n = UpsertMemoryNode()

    @contextmanager
    def _session_scope():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    n._session_scope = _session_scope  # noqa: SLF001 -- test seam injection
    n._embed = lambda text: _STUB_EMBEDDING  # noqa: SLF001 -- avoid live provider
    return n


def _seed_fact(session_factory, **overrides) -> SemanticMemory:
    defaults = dict(
        peer_id="client-acme",
        fact="Acme was quoted $150/hr for the WhatsApp automation project.",
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


class TestNonContradictingInsert:
    def test_inserts_new_row_with_supplied_confidence(self, node, session_factory):
        upserted = node.upsert_facts(
            peer_id="client-acme",
            facts=[{"fact": "Acme is a mid-market retailer.", "confidence": 0.85}],
        )
        assert len(upserted) == 1
        assert upserted[0].confidence == 0.85
        assert upserted[0].fact == "Acme is a mid-market retailer."
        assert list(upserted[0].embedding) == _STUB_EMBEDDING

        with session_factory() as session:
            assert session.query(SemanticMemory).count() == 1

    def test_default_confidence_when_not_supplied(self, node):
        upserted = node.upsert_facts(
            peer_id="client-acme", facts=[{"fact": "No confidence supplied."}]
        )
        assert upserted[0].confidence == 0.9

    def test_default_decay_factor_when_not_supplied(self, node):
        upserted = node.upsert_facts(peer_id="client-acme", facts=[{"fact": "Some fact."}])
        assert upserted[0].decay_factor == 0.95

    def test_evidence_episode_ids_default_from_batch_level(self, node):
        upserted = node.upsert_facts(
            peer_id="client-acme",
            facts=[{"fact": "Some fact."}],
            evidence_episode_ids=["episode-1"],
        )
        assert upserted[0].evidence_episode_ids == ["episode-1"]

    def test_per_fact_evidence_episode_ids_override_batch_level(self, node):
        upserted = node.upsert_facts(
            peer_id="client-acme",
            facts=[{"fact": "Some fact.", "evidence_episode_ids": ["episode-2"]}],
            evidence_episode_ids=["episode-1"],
        )
        assert upserted[0].evidence_episode_ids == ["episode-2"]

    def test_multiple_facts_in_one_batch_all_inserted(self, node, session_factory):
        upserted = node.upsert_facts(
            peer_id="client-acme",
            facts=[{"fact": "Fact A."}, {"fact": "Fact B."}, {"fact": "Fact C."}],
        )
        assert len(upserted) == 3
        with session_factory() as session:
            assert session.query(SemanticMemory).count() == 3


class TestContradictionHandling:
    def test_old_confidence_drops_new_row_created_old_row_intact(
        self, node, session_factory
    ):
        original = _seed_fact(session_factory, confidence=0.9)

        upserted = node.upsert_facts(
            peer_id="client-acme",
            facts=[
                {
                    "fact": "Acme's rate was later renegotiated to $175/hr.",
                    "confidence": 0.9,
                    "contradicts_fact_id": original.id,
                }
            ],
        )

        assert len(upserted) == 1
        assert upserted[0].fact == "Acme's rate was later renegotiated to $175/hr."

        with session_factory() as session:
            assert session.query(SemanticMemory).count() == 2
            preserved = session.query(SemanticMemory).filter_by(id=original.id).one()
            assert preserved.confidence < 0.9
            assert preserved.fact == original.fact

    def test_contradiction_applies_decay_before_lowering(self, node, session_factory):
        updated_at = datetime(2026, 1, 1)
        original = _seed_fact(
            session_factory, confidence=0.9, decay_factor=0.95, updated_at=updated_at
        )
        weeks_elapsed = 6

        with freeze_time(updated_at + timedelta(weeks=weeks_elapsed)):
            node.upsert_facts(
                peer_id="client-acme",
                facts=[
                    {
                        "fact": "Contradicting fact.",
                        "contradicts_fact_id": original.id,
                    }
                ],
            )

        expected_decayed = effective_confidence(0.9, 0.95, weeks_elapsed)
        expected_final = expected_decayed * CONTRADICTION_PENALTY

        with session_factory() as session:
            preserved = session.query(SemanticMemory).filter_by(id=original.id).one()
            assert preserved.confidence == pytest.approx(expected_final)

    def test_contradicting_a_missing_fact_id_does_not_raise(self, node, session_factory):
        import uuid

        upserted = node.upsert_facts(
            peer_id="client-acme",
            facts=[
                {
                    "fact": "Contradicts a row that doesn't exist.",
                    "contradicts_fact_id": uuid.uuid4(),
                }
            ],
        )
        assert len(upserted) == 1
        with session_factory() as session:
            assert session.query(SemanticMemory).count() == 1

    def test_contradicted_row_is_never_deleted(self, node, session_factory):
        original = _seed_fact(session_factory)
        node.upsert_facts(
            peer_id="client-acme",
            facts=[{"fact": "New fact.", "contradicts_fact_id": original.id}],
        )
        with session_factory() as session:
            assert (
                session.query(SemanticMemory).filter_by(id=original.id).first()
                is not None
            )


class TestProcess:
    """process() reads the upstream node's {"result": ...} contract (rule 9)."""

    def test_process_reads_upstream_node_and_writes_result(self, node):
        ctx = TaskContext(event={})
        ctx.nodes["IngestTimeExtractionNode"] = {
            "result": {
                "peer_id": "client-acme",
                "facts": [{"fact": "Acme is a mid-market retailer.", "confidence": 0.8}],
                "evidence_episode_ids": ["episode-1"],
            }
        }

        result_ctx = node.process(ctx)

        output = result_ctx.get_node_output("UpsertMemoryNode")["result"]
        assert len(output["upserted"]) == 1
        assert output["upserted"][0]["fact"] == "Acme is a mid-market retailer."
        assert output["upserted"][0]["confidence"] == 0.8
        assert output["upserted"][0]["evidence_episode_ids"] == ["episode-1"]

    def test_process_uses_custom_source_node_name(self, session_factory):
        n = UpsertMemoryNode(source_node_name="ConsolidationNode")

        @contextmanager
        def _session_scope():
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

        n._session_scope = _session_scope  # noqa: SLF001
        n._embed = lambda text: _STUB_EMBEDDING  # noqa: SLF001

        ctx = TaskContext(event={})
        ctx.nodes["ConsolidationNode"] = {
            "result": {"peer_id": "client-acme", "facts": [{"fact": "Consolidated fact."}]}
        }

        result_ctx = n.process(ctx)
        output = result_ctx.get_node_output("UpsertMemoryNode")["result"]
        assert output["upserted"][0]["fact"] == "Consolidated fact."
