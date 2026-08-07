"""Tests for app/brain/query_log.py — OR.K1 task 2.

Covers `log_retrieval`'s row shape (`via_mix`, `top_doc_ids`, `top_score`,
`abstained` derivation), the test-suite inertness switch
(`BRAIN_QUERY_LOG_ENABLED`, forced off by the autouse `_disable_query_log`
fixture and opted back in via `enable_query_log`), the fire-and-forget
discipline (a forced session failure is swallowed with a warning, never
raised), and surface threading from the three thin adapters (`syn recall` ->
"cli", `GET /recall` -> "http", `RetrieveChunksNode` -> "workflow") through
to a single logged row.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from brain import query_log, retrieval_engine
from database.retrieval_query import RetrievalQuery
from database.session import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _fake_sqlite_db_session_factory():
    """Build an in-memory SQLite engine/session-factory pair mirroring the
    shape of `database.session.db_session` (commit on success, rollback on
    exception, always close)."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine, tables=[RetrievalQuery.__table__])
    session_factory = sessionmaker(bind=engine)

    def _db_session():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return engine, session_factory, _db_session


@pytest.fixture
def query_log_db(monkeypatch):
    """Wire `query_log.db_session` to a fresh in-memory `retrieval_queries` table."""
    engine, session_factory, fake_db_session = _fake_sqlite_db_session_factory()
    monkeypatch.setattr(query_log, "db_session", fake_db_session)
    yield session_factory
    engine.dispose()


def _fake_results(*, vias=("semantic", "semantic", "keyword"), doc_ids=None):
    doc_ids = doc_ids or [f"doc-{i}" for i in range(len(vias))]
    return [
        {"doc_id": doc_ids[i], "via": vias[i], "score": 1.0 - i * 0.1}
        for i in range(len(vias))
    ]


# ---------------------------------------------------------------------------
# Test-suite inertness
# ---------------------------------------------------------------------------


class TestInertness:
    """`BRAIN_QUERY_LOG_ENABLED` gates the write; off by default in the suite."""

    def test_default_inert_writes_zero_rows(self, query_log_db):
        # The top-level autouse fixture (tests/conftest.py) already forces
        # BRAIN_QUERY_LOG_ENABLED=0 for this test — no opt-in fixture here.
        query_log.log_retrieval(
            "q",
            _fake_results(),
            surface="cli",
            workspace_id=None,
            hybrid=True,
            retrieval_confidence=0.9,
            latency_ms=5,
        )
        session = query_log_db()
        assert session.query(RetrievalQuery).count() == 0
        session.close()

    def test_enable_query_log_fixture_turns_writes_on(self, query_log_db, enable_query_log):
        query_log.log_retrieval(
            "q",
            _fake_results(),
            surface="cli",
            workspace_id=None,
            hybrid=True,
            retrieval_confidence=0.9,
            latency_ms=5,
        )
        session = query_log_db()
        assert session.query(RetrievalQuery).count() == 1
        session.close()


# ---------------------------------------------------------------------------
# Row contents
# ---------------------------------------------------------------------------


class TestRowContents:
    def test_via_mix_matches_result_via_fields(self, query_log_db, enable_query_log):
        results = _fake_results(vias=("semantic", "semantic", "keyword", "structural"))
        query_log.log_retrieval(
            "what changed",
            results,
            surface="http",
            workspace_id="orchestrator",
            hybrid=True,
            retrieval_confidence=0.9,
            latency_ms=12,
        )
        session = query_log_db()
        row = session.query(RetrievalQuery).one()
        assert row.via_mix == {"semantic": 2, "keyword": 1, "structural": 1}
        assert row.result_count == 4
        assert row.top_doc_ids == [r["doc_id"] for r in results[:5]]
        assert row.top_score == results[0]["score"]
        assert row.surface == "http"
        assert row.workspace_id == "orchestrator"
        assert row.hybrid is True
        assert row.query == "what changed"
        session.close()

    def test_top_doc_ids_capped_at_five(self, query_log_db, enable_query_log):
        results = _fake_results(vias=("semantic",) * 8)
        query_log.log_retrieval(
            "q",
            results,
            surface="cli",
            workspace_id=None,
            hybrid=True,
            retrieval_confidence=0.9,
            latency_ms=1,
        )
        session = query_log_db()
        row = session.query(RetrievalQuery).one()
        assert row.top_doc_ids == [r["doc_id"] for r in results[:5]]
        session.close()

    def test_abstain_true_below_threshold(self, query_log_db, enable_query_log):
        query_log.log_retrieval(
            "q",
            [],
            surface="cli",
            workspace_id=None,
            hybrid=False,
            retrieval_confidence=query_log.ABSTAIN_THRESHOLD - 0.01,
            latency_ms=1,
        )
        session = query_log_db()
        row = session.query(RetrievalQuery).one()
        assert row.abstained is True
        assert row.result_count == 0
        assert row.top_score is None
        session.close()

    def test_abstain_false_at_or_above_threshold(self, query_log_db, enable_query_log):
        query_log.log_retrieval(
            "q",
            _fake_results(vias=("semantic",)),
            surface="cli",
            workspace_id=None,
            hybrid=False,
            retrieval_confidence=query_log.ABSTAIN_THRESHOLD,
            latency_ms=1,
        )
        session = query_log_db()
        row = session.query(RetrievalQuery).one()
        assert row.abstained is False
        session.close()

    def test_abstain_false_when_confidence_none(self, query_log_db, enable_query_log):
        query_log.log_retrieval(
            "q",
            [],
            surface="cli",
            workspace_id=None,
            hybrid=False,
            retrieval_confidence=None,
            latency_ms=1,
        )
        session = query_log_db()
        row = session.query(RetrievalQuery).one()
        assert row.abstained is False
        assert row.retrieval_confidence is None
        session.close()

    def test_surface_none_stored_as_unknown(self, query_log_db, enable_query_log):
        query_log.log_retrieval(
            "q",
            [],
            surface=None,
            workspace_id=None,
            hybrid=False,
            retrieval_confidence=None,
            latency_ms=1,
        )
        session = query_log_db()
        row = session.query(RetrievalQuery).one()
        assert row.surface == "unknown"
        session.close()


# ---------------------------------------------------------------------------
# Fire-and-forget discipline
# ---------------------------------------------------------------------------


class TestFireAndForget:
    def test_session_failure_is_swallowed_and_warned(self, enable_query_log, caplog):
        def _raising_db_session():
            raise RuntimeError("boom")
            yield  # pragma: no cover - unreachable; keeps this a generator function

        with patch.object(query_log, "db_session", _raising_db_session):
            with caplog.at_level("WARNING"):
                query_log.log_retrieval(
                    "q",
                    [],
                    surface="cli",
                    workspace_id=None,
                    hybrid=False,
                    retrieval_confidence=None,
                    latency_ms=1,
                )

        assert any(
            "retrieval query log write failed" in record.message for record in caplog.records
        )

    def test_retrieve_still_returns_results_when_logging_fails(self, enable_query_log, caplog):
        """A forced logging failure must never fail or roll back `retrieve()`."""
        candidate = {
            "id": uuid.uuid4(),
            "content": "some content",
            "section_title": None,
            "is_section_title": False,
            "distance": 0.1,
            "file_path": None,
            "doc_id": "D1",
            "title": None,
            "authored_at": None,
            "via": "semantic",
        }
        fake_embedder = MagicMock()
        fake_embedder.embed_text.return_value = [0.1, 0.2]

        def _raising_db_session():
            raise RuntimeError("closed engine")
            yield  # pragma: no cover - unreachable

        with (
            patch("brain.retrieval_engine._semantic_search", return_value=[candidate]),
            patch("brain.retrieval_engine._keyword_search", return_value=set()),
            patch.object(query_log, "db_session", _raising_db_session),
            caplog.at_level("WARNING"),
        ):
            results = retrieval_engine.retrieve(
                "what changed",
                corpus="content",
                k=5,
                embedder=fake_embedder,
                surface="workflow",
            )

        assert len(results) == 1
        assert any(
            "retrieval query log write failed" in record.message for record in caplog.records
        )


# ---------------------------------------------------------------------------
# Surface threading — the single choke point covers every surface
# ---------------------------------------------------------------------------


class TestSurfaceThreading:
    def test_retrieve_logs_one_row_with_surface_workflow(self, query_log_db, enable_query_log):
        """`RetrieveChunksNode` calls `retrieve()` directly with `surface="workflow"`."""
        candidate = {
            "id": uuid.uuid4(),
            "content": "some content",
            "section_title": None,
            "is_section_title": False,
            "distance": 0.1,
            "file_path": None,
            "doc_id": "D1",
            "title": None,
            "authored_at": None,
            "via": "semantic",
        }
        fake_embedder = MagicMock()
        fake_embedder.embed_text.return_value = [0.1, 0.2]

        with (
            patch("brain.retrieval_engine._semantic_search", return_value=[candidate]),
            patch("brain.retrieval_engine._keyword_search", return_value=set()),
        ):
            results = retrieval_engine.retrieve(
                "what changed",
                corpus="content",
                k=5,
                embedder=fake_embedder,
                surface="workflow",
            )

        assert len(results) == 1
        session = query_log_db()
        row = session.query(RetrievalQuery).one()
        assert row.surface == "workflow"
        assert row.hybrid is True
        assert row.via_mix == {"semantic": 1}
        session.close()

    def test_run_eval_logs_one_row_with_surface_eval(self, query_log_db, enable_query_log):
        """`run_eval`'s `retrieve()` call stamps `surface="eval"` — the only
        genuine plumbing gap this block closes (the other three surfaces
        were already landed in `a660715`)."""
        from brain.eval.models import RetrievalCase
        from brain.eval.runner import run_eval

        candidate = {
            "id": uuid.uuid4(),
            "content": "some content",
            "section_title": None,
            "is_section_title": False,
            "distance": 0.1,
            "file_path": None,
            "doc_id": "D1",
            "title": None,
            "authored_at": None,
            "via": "semantic",
        }
        case = RetrievalCase(
            case_id="fixture-eval-surface",
            query="what changed",
            expect_docs=(),
            expect_abstain=True,
        )
        fake_embedder = MagicMock()
        fake_embedder.embed_text.return_value = [0.1, 0.2]

        with (
            patch("brain.retrieval_engine._semantic_search", return_value=[candidate]),
            patch("brain.retrieval_engine._keyword_search", return_value=set()),
        ):
            run_eval([case], corpus="content", session=MagicMock(), embedder=fake_embedder)

        session = query_log_db()
        row = session.query(RetrievalQuery).one()
        assert row.surface == "eval"
        session.close()

    def test_workflow_node_passes_surface_workflow(self):
        from core.task import TaskContext
        from workflows.document_qa_workflow_nodes.retrieve_chunks_node import (
            RetrieveChunksNode,
        )

        event = MagicMock()
        event.question = "q"
        event.corpus = "content"
        ctx = TaskContext(event=event)

        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.retrieval_engine.retrieve",
            return_value=[],
        ) as mock_retrieve:
            RetrieveChunksNode().process(ctx)

        assert mock_retrieve.call_args.kwargs["surface"] == "workflow"

    def test_cli_recall_passes_surface_cli(self):
        from brain.cli import main

        with patch("brain.retrieval.recall", return_value=[]) as mock_recall:
            main(["recall", "q", "--json"])

        assert mock_recall.call_args.kwargs["surface"] == "cli"

    def test_http_route_passes_surface_http(self):
        from api.read import recall_route

        with patch("api.read.retrieval.recall", return_value=[]) as mock_recall:
            recall_route(q="q", limit=5, hybrid=False, session=MagicMock())

        assert mock_recall.call_args.kwargs["surface"] == "http"

    def test_recall_exact_id_path_logs_one_row(self, query_log_db, enable_query_log):
        from brain.retrieval import recall

        fake_doc = MagicMock()
        fake_doc.doc_id = "D20"
        fake_doc.file_path = "docs/decisions/D20.md"
        fake_doc.title = "D20"
        fake_doc.section = ""
        fake_doc.content = "content"

        fake_session = MagicMock()
        with patch("brain.retrieval.exact_id_lookup", return_value=[fake_doc]):
            results = recall("What is D20?", session=fake_session, surface="cli")

        assert results[0]["via"] == "exact-id"
        session = query_log_db()
        row = session.query(RetrievalQuery).one()
        assert row.surface == "cli"
        assert row.hybrid is False
        assert row.via_mix == {"exact-id": 1}
        session.close()
