"""Tests for app/brain/cli.py — the `syn` dispatcher (OR.N1 task 4).

Dispatches each subcommand via `main([...])` with the read cores patched,
asserting argument wiring, that `--json` output parses as JSON and is the
sole stdout payload, deterministic exit codes (`pulse` unhealthy -> non-zero,
healthy -> 0; unknown `--workspace` -> non-zero, no prompt/traceback), and
one end-to-end `recall`-parity check against `query_brain`'s hybrid path over
the `pgvector_engine` fixture. Also asserts the `[project.scripts]` `syn`
entry exists and `app.brain.cli:main` is importable/callable.
"""

import importlib
import json
import sys
import tomllib
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from brain.cli import main
from brain.pulse import PulseReport
from database.retrieval_query import RetrievalQuery
from database.session import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _read_stdout(capsys) -> str:
    return capsys.readouterr().out


class TestRecallDispatch:
    """`syn recall` wires argparse args to `brain.retrieval.recall`."""

    def test_recall_json_emits_sole_parseable_payload(self, capsys):
        fake_results = [{"doc_id": "D20", "file_path": "docs/decisions/D20.md", "title": "D20"}]
        with patch("brain.retrieval.recall", return_value=fake_results) as mock_recall:
            code = main(["recall", "what is D20", "--limit", "3", "--hybrid", "--json"])

        assert code == 0
        mock_recall.assert_called_once_with(
            "what is D20", limit=3, hybrid=True, workspace=None, surface="cli", corpus="brain"
        )
        out = _read_stdout(capsys)
        assert json.loads(out) == fake_results

    def test_recall_human_mode_does_not_emit_raw_json(self, capsys):
        fake_results = [{"doc_id": "D20", "file_path": "docs/decisions/D20.md", "title": "D20"}]
        with patch("brain.retrieval.recall", return_value=fake_results):
            code = main(["recall", "what is D20"])

        assert code == 0
        out = _read_stdout(capsys)
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)

    def test_recall_unknown_workspace_returns_nonzero_no_traceback(self, capsys):
        from services.workspace_resolver import UnknownWorkspaceError

        with patch(
            "services.workspace_resolver.resolve_workspace_root",
            side_effect=UnknownWorkspaceError("nope"),
        ):
            code = main(["recall", "some query", "--workspace", "nope", "--json"])

        assert code != 0
        out = _read_stdout(capsys)
        payload = json.loads(out)
        assert "error" in payload


class TestWalkDispatch:
    """`syn walk` wires argparse args to `brain.graph.walk`."""

    def test_walk_json_emits_sole_parseable_payload(self, capsys):
        fake_result = {"root": "D36", "depth": 1, "levels": [["D41"]], "nodes": {}}
        with patch("brain.graph.walk", return_value=fake_result) as mock_walk:
            code = main(["walk", "D36", "--depth", "1", "--json"])

        assert code == 0
        mock_walk.assert_called_once_with("D36", depth=1)
        out = _read_stdout(capsys)
        assert json.loads(out) == fake_result


class TestPulseDispatch:
    """`syn pulse` maps the health verdict to the process exit code."""

    def test_pulse_healthy_returns_zero(self, capsys):
        report = PulseReport(
            pgvector_reachable=True,
            embedding_reachable=True,
            embedding_error=None,
            brain_documents_count=10,
            brain_edges_count=5,
            max_indexed_at=None,
            max_authored_at=None,
            edges_empty_but_related_exists=False,
            healthy=True,
        )
        with patch("brain.pulse.pulse", return_value=report):
            code = main(["pulse", "--json"])

        assert code == 0
        out = _read_stdout(capsys)
        payload = json.loads(out)
        assert payload["healthy"] is True

    def test_pulse_unhealthy_returns_nonzero(self, capsys):
        report = PulseReport(
            pgvector_reachable=True,
            embedding_reachable=True,
            embedding_error=None,
            brain_documents_count=10,
            brain_edges_count=0,
            max_indexed_at=None,
            max_authored_at=None,
            edges_empty_but_related_exists=True,
            healthy=False,
        )
        with patch("brain.pulse.pulse", return_value=report):
            code = main(["pulse", "--json"])

        assert code != 0
        out = _read_stdout(capsys)
        payload = json.loads(out)
        assert payload["healthy"] is False


class TestEvalDispatch:
    """`syn eval --no-write` (task 1, `ticket-eval-plumbing-and-golden-set-v2`).

    `--no-write` gates persistence only: `write_report` is never called and
    the JSON payload's `written_path` is `null`, but scored metrics and the
    `--baseline` regression verdict are identical to a plain run.
    """

    @staticmethod
    def _fake_eval_report(**agg_overrides):
        from brain.eval.models import CaseResult, RetrievalRunReport

        aggregate = {
            "recall_at_5": 0.5,
            "recall_at_10": 0.6,
            "mrr": 0.4,
            "groundedness": 0.3,
            "groundedness_on_hits": 0.5,
            "abstain_correctness": 0.9,
        }
        aggregate.update(agg_overrides)
        result = CaseResult(
            case_id="archive-01-rates",
            recall_at_5=1.0,
            recall_at_10=1.0,
            reciprocal_rank=1.0,
            predicted_abstain=False,
            expected_abstain=False,
            abstain_correct=True,
            groundedness=1.0,
            retrieval_confidence=0.9,
            matched_docs=("docs/x.md",),
        )
        return RetrievalRunReport(
            generated_at="2026-08-07T00-00-00Z",
            case_count=1,
            results=(result,),
            aggregate=aggregate,
            corpus={
                "chunk_count": 1,
                "file_count": 1,
                "edge_count": 0,
                "max_indexed_at": None,
            },
            ranking_constants={"kw_weight": 0.3},
        )

    def test_no_write_creates_no_file_and_matches_plain_run_metrics(self, capsys):
        report = self._fake_eval_report()
        with (
            patch("brain.eval.load_cases", return_value=[]),
            patch("brain.eval.run_eval", return_value=report),
            patch("brain.eval.write_report") as mock_write,
        ):
            code = main(["eval", "--no-write", "--json"])

        assert code == 0
        mock_write.assert_not_called()
        payload = json.loads(_read_stdout(capsys))
        assert payload["written_path"] is None
        assert payload["aggregate"] == report.aggregate

    def test_plain_run_writes_report_and_emits_written_path(self, capsys, tmp_path):
        report = self._fake_eval_report()
        written = tmp_path / "2026-08-07T00-00-00Z.json"
        with (
            patch("brain.eval.load_cases", return_value=[]),
            patch("brain.eval.run_eval", return_value=report),
            patch("brain.eval.write_report", return_value=written) as mock_write,
        ):
            code = main(["eval", "--json"])

        assert code == 0
        mock_write.assert_called_once_with(report)
        payload = json.loads(_read_stdout(capsys))
        assert payload["written_path"] == str(written)

    def test_no_write_human_mode_prints_not_persisted_marker(self, capsys):
        report = self._fake_eval_report()
        with (
            patch("brain.eval.load_cases", return_value=[]),
            patch("brain.eval.run_eval", return_value=report),
            patch("brain.eval.write_report") as mock_write,
        ):
            code = main(["eval", "--no-write"])

        assert code == 0
        mock_write.assert_not_called()
        out = _read_stdout(capsys)
        assert "(--no-write: report not persisted)" in out

    def test_plain_run_human_mode_omits_not_persisted_marker(self, capsys):
        report = self._fake_eval_report()
        with (
            patch("brain.eval.load_cases", return_value=[]),
            patch("brain.eval.run_eval", return_value=report),
            patch("brain.eval.write_report", return_value=Path("/tmp/fake.json")),
        ):
            code = main(["eval"])

        assert code == 0
        out = _read_stdout(capsys)
        assert "(--no-write: report not persisted)" not in out

    def test_no_write_with_regressing_baseline_still_exits_nonzero(self, capsys, tmp_path):
        """Amendment (plan-eval-statistical-honesty task 3): the fixture's
        single `results` case is hardcoded to `recall_at_5=1.0` on both
        sides regardless of the `aggregate` override, so the paired verdict
        correctly reads it as unchanged (`flat`, not `regressed-significant`)
        even though the synthetic `aggregate` numbers moved. `--strict`
        restores the pre-task-3 strict-sign tripwire this test was written
        against — same pattern as `test_cli_eval_baseline_exits_non_zero_
        on_seeded_regression` in `test_eval.py`."""
        report = self._fake_eval_report(recall_at_5=0.1)
        baseline_path = tmp_path / "baseline.json"
        baseline_report = self._fake_eval_report(recall_at_5=0.9)
        baseline_path.write_text(json.dumps(baseline_report.to_dict()), encoding="utf-8")

        with (
            patch("brain.eval.load_cases", return_value=[]),
            patch("brain.eval.run_eval", return_value=report),
            patch("brain.eval.write_report") as mock_write,
        ):
            code = main(
                ["eval", "--no-write", "--baseline", str(baseline_path), "--strict", "--json"]
            )

        assert code == 1
        mock_write.assert_not_called()
        payload = json.loads(_read_stdout(capsys))
        assert payload["written_path"] is None
        assert payload["baseline_deltas"]["recall_at_5"] < 0


class TestEvalReportDispatch:
    """`syn eval --report [PATH]` (task 4, `OR.ticket.publishable-eval-report`).

    `--report` composes with every other eval flag; the renderer itself is
    patched here since its scrub/allow-list behavior is covered by
    `tests/brain/test_eval_report.py` — this class only asserts CLI wiring:
    argument parsing (with and without a value) and that the handler writes
    to stdout or to the named path.
    """

    def test_report_without_value_writes_to_stdout(self, capsys):
        report = TestEvalDispatch._fake_eval_report()
        with (
            patch("brain.eval.load_cases", return_value=[]),
            patch("brain.eval.run_eval", return_value=report),
            patch("brain.eval.write_report"),
            patch("brain.eval.report.render_run", return_value="# rendered report") as mock_render,
        ):
            code = main(["eval", "--no-write", "--report"])

        assert code == 0
        mock_render.assert_called_once_with(report)
        out = _read_stdout(capsys)
        assert "# rendered report" in out

    def test_report_with_path_writes_the_file_not_stdout(self, capsys, tmp_path):
        report = TestEvalDispatch._fake_eval_report()
        out_path = tmp_path / "report.md"
        with (
            patch("brain.eval.load_cases", return_value=[]),
            patch("brain.eval.run_eval", return_value=report),
            patch("brain.eval.write_report"),
            patch("brain.eval.report.render_run", return_value="# rendered report") as mock_render,
        ):
            code = main(["eval", "--no-write", "--report", str(out_path)])

        assert code == 0
        mock_render.assert_called_once_with(report)
        assert out_path.read_text(encoding="utf-8") == "# rendered report"
        out = _read_stdout(capsys)
        assert "# rendered report" not in out

    def test_report_omitted_renders_nothing(self, capsys):
        report = TestEvalDispatch._fake_eval_report()
        with (
            patch("brain.eval.load_cases", return_value=[]),
            patch("brain.eval.run_eval", return_value=report),
            patch("brain.eval.write_report"),
            patch("brain.eval.report.render_run") as mock_render,
        ):
            code = main(["eval", "--no-write"])

        assert code == 0
        mock_render.assert_not_called()

    def test_report_composes_with_json_output(self, capsys):
        report = TestEvalDispatch._fake_eval_report()
        with (
            patch("brain.eval.load_cases", return_value=[]),
            patch("brain.eval.run_eval", return_value=report),
            patch("brain.eval.write_report"),
            patch("brain.eval.report.render_run", return_value="# rendered report"),
        ):
            code = main(["eval", "--no-write", "--json", "--report"])

        assert code == 0
        out = _read_stdout(capsys)
        first_line = out.splitlines()[0]
        payload = json.loads(first_line)
        assert payload["written_path"] is None
        assert "# rendered report" in out


def _fake_report(**overrides):
    from brain.reconcile import ReconcileReport

    defaults = dict(
        deleted_but_embedded=[],
        section_orphans=[],
        orphaned_chunks=[],
        dangling_edges=[],
        model_mismatch=[],
        unstamped_count=0,
        ingested_count=0,
        ingested_min_authored_at=None,
        ingested_max_authored_at=None,
        drift=False,
    )
    defaults.update(overrides)
    return ReconcileReport(**defaults)


class TestStaleDeepDispatch:
    """`syn stale --deep [--repair]` wires to `reconcile.deep_stale` / `ops.repair_deep_stale`."""

    def test_healthy_json_exits_zero(self, capsys):
        report = _fake_report()
        with patch("brain.reconcile.deep_stale", return_value=report) as mock_deep_stale:
            code = main(["stale", "--deep", "--json", "--brain-path", "/tmp/brain"])

        assert code == 0
        mock_deep_stale.assert_called_once_with(brain_path="/tmp/brain")
        out = _read_stdout(capsys)
        payload = json.loads(out)
        assert payload["drift"] is False

    def test_drifted_json_exits_nonzero(self, capsys):
        report = _fake_report(deleted_but_embedded=["gone.md"], drift=True)
        with patch("brain.reconcile.deep_stale", return_value=report):
            code = main(["stale", "--deep", "--json"])

        assert code == 1
        out = _read_stdout(capsys)
        payload = json.loads(out)
        assert payload["drift"] is True
        assert payload["deleted_but_embedded"] == ["gone.md"]

    def test_human_mode_does_not_emit_raw_json(self, capsys):
        report = _fake_report()
        with patch("brain.reconcile.deep_stale", return_value=report):
            code = main(["stale", "--deep"])

        assert code == 0
        out = _read_stdout(capsys)
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)
        assert "drift: False" in out

    def test_repair_dispatches_and_reports_delta(self, capsys):
        before = _fake_report(deleted_but_embedded=["gone.md"], drift=True)
        after = _fake_report()
        repair_result = {
            "actions": [{"axis": "deleted_but_embedded", "action": "prune_paths", "count": 1}],
            "before": before.to_dict(),
            "after": after.to_dict(),
        }
        with patch("brain.reconcile.deep_stale", return_value=before), patch(
            "brain.ops.repair_deep_stale", return_value=repair_result
        ) as mock_repair:
            code = main(["stale", "--deep", "--repair", "--json"])

        assert code == 0
        mock_repair.assert_called_once_with(before, brain_path=None)
        out = _read_stdout(capsys)
        payload = json.loads(out)
        assert payload == repair_result

    def test_error_returns_nonzero_with_typed_payload(self, capsys):
        with patch("brain.reconcile.deep_stale", side_effect=RuntimeError("db down")):
            code = main(["stale", "--deep", "--json"])

        assert code != 0
        out = _read_stdout(capsys)
        payload = json.loads(out)
        assert payload["error"] == "db down"


class TestReconcileRoutineDispatch:
    """`syn routine reconcile` runs the deep check via `ops.run_routine`."""

    def test_runs_and_emits_json(self, capsys):
        report = _fake_report()
        with patch("brain.reconcile.deep_stale", return_value=report):
            code = main(["routine", "reconcile", "--json"])

        assert code == 0
        out = _read_stdout(capsys)
        payload = json.loads(out)
        assert payload["drift"] is False


class TestConsoleScriptRegistration:
    """`[project.scripts]` registers `syn = "app.brain.cli:main"` and it is callable."""

    def test_pyproject_declares_syn_entry(self):
        pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = pyproject["project"]["scripts"]
        assert scripts["syn"] == "app.brain.cli:main"

    def test_app_brain_cli_main_is_importable_and_callable(self):
        module = importlib.import_module("app.brain.cli")
        assert callable(module.main)


class TestSysPathShim:
    """`main()` inserts `app/` onto `sys.path` so package-relative imports resolve."""

    def test_app_dir_present_after_cli_import_and_dispatch(self):
        with patch("brain.pulse.pulse") as mock_pulse:
            mock_pulse.return_value = PulseReport(
                pgvector_reachable=True,
                embedding_reachable=True,
                embedding_error=None,
                brain_documents_count=0,
                brain_edges_count=0,
                max_indexed_at=None,
                max_authored_at=None,
                edges_empty_but_related_exists=False,
                healthy=True,
            )
            main(["pulse", "--json"])

        app_dir = str(_REPO_ROOT / "app")
        assert app_dir in sys.path


class TestRecallParityEndToEnd:
    """`syn recall --hybrid` parity against `query_brain`'s (`brain.retrieval.hybrid_search`) path.

    ``brain.retrieval_engine.retrieve`` is mocked (OR.K2 promoted the fusion
    pipeline out of ``RetrieveChunksNode``) so this exercises the real
    dispatch chain — argparse -> `brain.retrieval.recall` ->
    `brain.retrieval.hybrid_search` -> `brain.retrieval_engine.retrieve` ->
    `--json` stdout — without requiring a live embedding backend, while still
    proving `syn recall --hybrid` and `query_brain.py --hybrid` (which also
    calls `hybrid_search`) resolve to one implementation.
    """

    def test_recall_hybrid_matches_hybrid_search(self, capsys):
        from brain.retrieval import hybrid_search

        fake_engine_chunks = [
            {
                "id": "chunk-1",
                "doc_id": "D99",
                "file_path": "docs/decisions/D99-example.md",
                "title": "D99 — Parity Check",
                "section_title": "",
                "content": "Parity check content for the syn recall CLI.",
                "source": "General",
                "score": 0.9,
                "via": "semantic",
            }
        ]
        with patch("brain.retrieval_engine.retrieve", return_value=fake_engine_chunks):
            expected = hybrid_search("D99", limit=5)

            code = main(["recall", "D99", "--hybrid", "--json"])

        assert code == 0
        out = _read_stdout(capsys)
        assert json.loads(out) == expected
        assert expected == [
            {
                "doc_id": "D99",
                "file_path": "docs/decisions/D99-example.md",
                "title": "D99 — Parity Check",
                "section": "",
                "content": "Parity check content for the syn recall CLI.",
                "score": 0.9,
                "via": "semantic",
            }
        ]


def _sqlite_db_session_factory():
    """Build an in-memory SQLite `retrieval_queries` engine/session-factory pair
    mirroring `database.session.db_session`'s commit/rollback/close shape."""
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


def _make_row(session_factory, **overrides) -> None:
    defaults = dict(
        query="what changed in OR.K2?",
        surface="cli",
        workspace_id=None,
        hybrid=True,
        via_mix={"semantic": 2, "keyword": 1},
        result_count=3,
        top_score=0.9,
        retrieval_confidence=0.8,
        abstained=False,
        top_doc_ids=["doc-1"],
        latency_ms=12,
        created_at=datetime.now(),
    )
    defaults.update(overrides)
    session = session_factory()
    session.add(RetrievalQuery(**defaults))
    session.commit()
    session.close()


class TestQueriesDispatch:
    """`syn queries` reads raw `retrieval_queries` rows (OR.K1 task 3) — no aggregation
    table, no rollup: `--json` computes `abstain_rate` at read time over the window."""

    @pytest.fixture
    def queries_db(self):
        engine, session_factory, fake_db_session = _sqlite_db_session_factory()
        with patch("database.session.db_session", fake_db_session):
            yield session_factory
        engine.dispose()

    def test_json_returns_rows_count_and_abstain_rate(self, queries_db, capsys):
        _make_row(queries_db, query="q1", abstained=False)
        _make_row(queries_db, query="q2", abstained=True, retrieval_confidence=0.1)

        code = main(["queries", "--json"])

        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        assert payload["count"] == 2
        assert payload["abstain_rate"] == pytest.approx(0.5)
        assert {row["query"] for row in payload["queries"]} == {"q1", "q2"}

    def test_json_abstain_rate_zero_when_no_rows(self, queries_db, capsys):
        code = main(["queries", "--json"])

        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        assert payload["count"] == 0
        assert payload["abstain_rate"] == 0.0
        assert payload["queries"] == []

    def test_abstained_flag_filters_to_abstained_rows_only(self, queries_db, capsys):
        _make_row(queries_db, query="kept", abstained=False)
        _make_row(queries_db, query="dropped", abstained=True, retrieval_confidence=0.1)

        code = main(["queries", "--abstained", "--json"])

        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        assert [row["query"] for row in payload["queries"]] == ["dropped"]

    def test_since_window_excludes_older_rows(self, queries_db, capsys):
        now = datetime.now()
        _make_row(queries_db, query="recent", created_at=now)
        _make_row(queries_db, query="stale", created_at=now - timedelta(days=30))

        code = main(["queries", "--since", "7d", "--json"])

        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        assert [row["query"] for row in payload["queries"]] == ["recent"]

    def test_via_mix_and_confidence_survive_round_trip(self, queries_db, capsys):
        _make_row(
            queries_db,
            query="mix check",
            via_mix={"semantic": 3, "structural": 1},
            retrieval_confidence=0.77,
        )

        code = main(["queries", "--json"])

        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        row = payload["queries"][0]
        assert row["via_mix"] == {"semantic": 3, "structural": 1}
        assert row["retrieval_confidence"] == pytest.approx(0.77)

    def test_invalid_since_window_returns_nonzero_typed_error(self, queries_db, capsys):
        code = main(["queries", "--since", "not-a-window", "--json"])

        assert code != 0
        payload = json.loads(_read_stdout(capsys))
        assert "error" in payload

    def test_human_mode_does_not_emit_raw_json(self, queries_db, capsys):
        _make_row(queries_db, query="human mode row")

        code = main(["queries"])

        assert code == 0
        out = _read_stdout(capsys)
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)

    def test_human_mode_no_rows_prints_message(self, queries_db, capsys):
        code = main(["queries"])

        assert code == 0
        out = _read_stdout(capsys)
        assert "No logged queries." in out


class TestQueriesPruneDispatch:
    """`syn queries --prune` is the retention surface over `brain.ops.prune_queries`.

    Deterministic exit codes (0 including a zero-deletion no-op), `--json` on
    every path, and mutual exclusion with the read filters.
    """

    @pytest.fixture
    def queries_db(self):
        engine, session_factory, fake_db_session = _sqlite_db_session_factory()
        with patch("database.session.db_session", fake_db_session):
            yield session_factory
        engine.dispose()

    def test_prune_deletes_old_rows_and_exits_zero(self, queries_db, capsys):
        now = datetime.now()
        _make_row(queries_db, query="recent", created_at=now)
        _make_row(queries_db, query="ancient", created_at=now - timedelta(days=400))

        code = main(["queries", "--prune", "--json"])

        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        assert payload["deleted"] == 1
        assert payload["kept"] == 1
        assert payload["keep_days"] == 90
        assert payload["dry_run"] is False

    def test_keep_days_narrows_the_window(self, queries_db, capsys):
        now = datetime.now()
        _make_row(queries_db, query="recent", created_at=now - timedelta(days=2))
        _make_row(queries_db, query="middling", created_at=now - timedelta(days=30))

        code = main(["queries", "--prune", "--keep-days", "7", "--json"])

        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        assert payload["keep_days"] == 7
        assert payload["deleted"] == 1

    def test_dry_run_reports_without_deleting(self, queries_db, capsys):
        now = datetime.now()
        _make_row(queries_db, query="ancient", created_at=now - timedelta(days=400))

        code = main(["queries", "--prune", "--dry-run", "--json"])

        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        assert payload["deleted"] == 1
        assert payload["dry_run"] is True

        # Nothing was actually removed — a follow-up read still sees the row.
        code = main(["queries", "--json"])
        assert code == 0
        assert json.loads(_read_stdout(capsys))["count"] == 1

    def test_zero_deletions_still_exits_zero(self, queries_db, capsys):
        _make_row(queries_db, query="recent", created_at=datetime.now())

        code = main(["queries", "--prune", "--json"])

        assert code == 0
        assert json.loads(_read_stdout(capsys))["deleted"] == 0

    def test_human_mode_does_not_emit_raw_json(self, queries_db, capsys):
        code = main(["queries", "--prune"])

        assert code == 0
        out = _read_stdout(capsys)
        assert "queries prune:" in out
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)

    def test_error_is_typed_and_nonzero(self, capsys):
        with patch("brain.ops.prune_queries", side_effect=RuntimeError("db is down")):
            code = main(["queries", "--prune", "--json"])

        assert code == 1
        assert json.loads(_read_stdout(capsys))["error"] == "db is down"

    @pytest.mark.parametrize(
        "argv",
        [
            ["queries", "--prune", "--since", "7d"],
            ["queries", "--prune", "--abstained"],
            ["queries", "--prune", "--since", "7d", "--abstained"],
        ],
    )
    def test_prune_is_mutually_exclusive_with_read_filters(self, argv):
        with pytest.raises(SystemExit) as excinfo:
            main(argv)

        assert excinfo.value.code == 2

    @pytest.mark.parametrize(
        "argv", [["queries", "--keep-days", "7"], ["queries", "--dry-run"]]
    )
    def test_retention_flags_require_prune(self, argv):
        with pytest.raises(SystemExit) as excinfo:
            main(argv)

        assert excinfo.value.code == 2


class TestQueriesMineDispatch:
    """`syn queries mine` (OR.2.E task 4) — a proper subcommand, not a third
    `queries` mode. Proposes reviewable golden-set candidates as a stdout-only
    YAML fragment; never writes `planning/retrieval-golden-set.yaml`."""

    @pytest.fixture
    def queries_db(self):
        engine, session_factory, fake_db_session = _sqlite_db_session_factory()
        with (
            patch("database.session.db_session", fake_db_session),
            patch("brain.query_mining._load_golden_set_queries", return_value=set()),
        ):
            yield session_factory
        engine.dispose()

    def test_mine_is_registered_as_a_subcommand_not_a_queries_flag(self):
        """`queries mine` must be its own subparser, per the spec's explicit
        instruction not to add a third mode on `queries` (`_validate_queries_args`
        is already at its complexity ceiling)."""
        with pytest.raises(SystemExit) as excinfo:
            main(["queries", "--mine"])
        assert excinfo.value.code == 2  # unrecognized flag, not a real mode

    def test_empty_log_prints_friendly_message_and_exits_zero(self, queries_db, capsys):
        code = main(["queries", "mine"])

        assert code == 0
        out = _read_stdout(capsys)
        assert "no" in out.lower()
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)

    def test_empty_log_json_exits_zero_with_empty_candidates(self, queries_db, capsys):
        code = main(["queries", "mine", "--json"])

        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        assert payload == {"candidates": [], "count": 0}

    def test_fragment_carries_fail_loud_id_and_empty_expect_docs(self, queries_db, capsys):
        _make_row(queries_db, query="genuinely unanswerable", abstained=True)
        _make_row(queries_db, query="genuinely unanswerable", abstained=True)

        code = main(["queries", "mine"])
        assert code == 0

        out = _read_stdout(capsys)
        document = yaml.safe_load(out)
        assert document["cases"], "fragment must contain at least one case"
        for case in document["cases"]:
            assert case["id"] == "RENAME ME"
            assert case["expect_docs"] == []
            assert case["source"] == "mined"
            assert case["category"] == "mined"
            assert "source_query_id" in case

    def test_fragment_fails_the_golden_set_schema_test_as_emitted(self, queries_db, capsys):
        """The lazy path must fail loudly: as emitted (unedited), every case
        fails `test_expect_docs_or_abstain_present_for_every_case` (empty
        expect_docs, expect_abstain=false) AND `test_id_prefix_agrees_with_category`
        (`RENAME ME` has no recognized id prefix) — mirroring the golden-set
        schema test's own rules without importing app/ into that pure-YAML
        test module."""
        _make_row(queries_db, query="genuinely unanswerable", abstained=True)
        _make_row(queries_db, query="genuinely unanswerable", abstained=True)

        code = main(["queries", "mine"])
        assert code == 0

        document = yaml.safe_load(_read_stdout(capsys))
        prefix_to_category = {
            "archive": "archive",
            "id": "identifier",
            "neg": "negative",
            "hijack": "hijack",
            "mined": "mined",
        }
        for case in document["cases"]:
            fails_expect_docs_or_abstain = not (case["expect_docs"] or case["expect_abstain"])
            prefix = case["id"].split("-", 1)[0]
            fails_id_prefix = prefix not in prefix_to_category
            assert fails_expect_docs_or_abstain or fails_id_prefix, (
                "an unedited mined case must fail at least one golden-set schema rule"
            )

    def test_fragment_parses_under_load_cases_once_filled(self, queries_db, capsys, tmp_path):
        from brain.eval import load_cases

        _make_row(queries_db, query="genuinely unanswerable", abstained=True)
        _make_row(queries_db, query="genuinely unanswerable", abstained=True)

        code = main(["queries", "mine"])
        assert code == 0

        document = yaml.safe_load(_read_stdout(capsys))
        for i, case in enumerate(document["cases"]):
            case["id"] = f"mined-{i}"
            case["expect_docs"] = ["some/doc.md"]

        filled_path = tmp_path / "filled.yaml"
        filled_path.write_text(yaml.safe_dump(document), encoding="utf-8")

        cases = load_cases(filled_path)
        assert len(cases) == len(document["cases"])
        assert cases[0].source == "mined"
        assert cases[0].category == "mined"

    def test_candidates_carry_source_and_category_and_source_query_id(self, queries_db, capsys):
        _make_row(queries_db, query="genuinely unanswerable", abstained=True)
        _make_row(queries_db, query="genuinely unanswerable", abstained=True)

        code = main(["queries", "mine", "--json"])
        assert code == 0

        payload = json.loads(_read_stdout(capsys))
        assert payload["count"] == 1
        candidate = payload["candidates"][0]
        assert candidate["class"] == "abstained"
        assert "rationale" in candidate and candidate["rationale"]
        assert candidate["source_query_id"]

    def test_json_emits_ranked_candidates_with_rationale(self, queries_db, capsys):
        for i in range(4):
            _make_row(
                queries_db,
                query=f"filler {i}",
                retrieval_confidence=0.95,
                abstained=False,
                top_scores=[0.95, 0.4],
            )
            _make_row(
                queries_db,
                query=f"filler {i}",
                retrieval_confidence=0.95,
                abstained=False,
                top_scores=[0.95, 0.4],
            )
        _make_row(
            queries_db,
            query="low conf outlier",
            retrieval_confidence=0.2,
            abstained=False,
            top_scores=[0.5, 0.4],
        )
        _make_row(
            queries_db,
            query="low conf outlier",
            retrieval_confidence=0.2,
            abstained=False,
            top_scores=[0.5, 0.4],
        )

        code = main(["queries", "mine", "--json"])
        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        by_query = {c["query"]: c for c in payload["candidates"]}
        assert by_query["low conf outlier"]["class"] == "low-confidence-answered"
        assert by_query["low conf outlier"]["rationale"]

    def test_golden_set_queries_are_excluded_from_mined_output(self, queries_db, capsys):
        _make_row(queries_db, query="already in the golden set", abstained=True)
        _make_row(queries_db, query="already in the golden set", abstained=True)
        _make_row(queries_db, query="brand new mined query", abstained=True)
        _make_row(queries_db, query="brand new mined query", abstained=True)

        with patch(
            "brain.query_mining._load_golden_set_queries",
            return_value={"already in the golden set"},
        ):
            code = main(["queries", "mine", "--json"])

        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        queries = {c["query"] for c in payload["candidates"]}
        assert "already in the golden set" not in queries
        assert "brand new mined query" in queries

    def test_eval_surface_rows_excluded_from_mined_output(self, queries_db, capsys):
        _make_row(queries_db, query="harness only", surface="eval", abstained=True)
        _make_row(queries_db, query="harness only", surface="eval", abstained=True)

        code = main(["queries", "mine", "--json"])

        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        assert payload["candidates"] == []

    def test_min_count_and_include_singletons_flags_thread_through(self, queries_db, capsys):
        _make_row(queries_db, query="seen once", abstained=True)

        code = main(["queries", "mine", "--json"])
        assert code == 0
        assert json.loads(_read_stdout(capsys))["candidates"] == []

        code = main(["queries", "mine", "--include-singletons", "--json"])
        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        assert [c["query"] for c in payload["candidates"]] == ["seen once"]

    def test_limit_flag_caps_candidate_count(self, queries_db, capsys):
        for i in range(3):
            _make_row(queries_db, query=f"unanswerable {i}", abstained=True)
            _make_row(queries_db, query=f"unanswerable {i}", abstained=True)

        code = main(["queries", "mine", "--limit", "1", "--json"])
        assert code == 0
        payload = json.loads(_read_stdout(capsys))
        assert payload["count"] == 1

    def test_golden_set_file_never_opened_for_writing_during_mine(self):
        """Asserts the golden set is never opened for writing during a mine
        run — uses the REAL default `_load_golden_set_queries` path (no
        monkeypatch of it) against a fresh in-memory DB, guarding only the
        file-open call itself so this exercises the actual golden-set
        loader, not a stub."""
        engine, session_factory, fake_db_session = _sqlite_db_session_factory()
        _make_row(session_factory, query="genuinely unanswerable", abstained=True)
        _make_row(session_factory, query="genuinely unanswerable", abstained=True)

        real_open = open

        def _guarded_open(file, mode="r", *args, **kwargs):  # noqa: A002
            if "golden-set" in str(file) and ("w" in mode or "a" in mode or "+" in mode):
                raise AssertionError(f"golden set opened for writing: mode={mode!r}")
            return real_open(file, mode, *args, **kwargs)

        try:
            with (
                patch("database.session.db_session", fake_db_session),
                patch("builtins.open", _guarded_open),
            ):
                code = main(["queries", "mine"])
        finally:
            engine.dispose()

        assert code == 0

    def test_human_mode_does_not_emit_raw_json(self, queries_db, capsys):
        _make_row(queries_db, query="genuinely unanswerable", abstained=True)
        _make_row(queries_db, query="genuinely unanswerable", abstained=True)

        code = main(["queries", "mine"])

        assert code == 0
        out = _read_stdout(capsys)
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)
