"""Unit tests for scripts/run_eval.py (Bastion Program Block OR.U, Task 7).

Tests cover:
- table aggregation output on a normal run
- --dry-run lists cases without executing or persisting
- --gate exit codes (0 keep / nonzero revert)
- --emit-routing JSON shape and quality-floor cheapest-model selection

Follows tests/test_index_brain.py's pattern: ``database.session.db_session``
is lazily imported inside ``main()``, so it is patched at its source module
path with a fake generator yielding a real in-memory session (backed by
tests/conftest.py's session-scoped ``db_engine``) seeded with fixture
``events`` rows — the coding slice's ``load_coding_records`` loader queries
that table. Each test uses a unique ``--models`` value so eval-run history
(keyed by slice_name + model_name) never leaks across tests sharing the
session-scoped in-memory engine.
"""

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure scripts/ is importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from database.event import Event  # noqa: E402
from run_eval import main  # noqa: E402
from schemas.sdlc_schema import (  # noqa: E402
    SDLCReviewVerdict,
    SDLCState,
    SDLCTask,
    SDLCTaskStatus,
    SDLCTelemetry,
)


def _task(task_id, status, attempt_count=1, max_attempts=3):
    return SDLCTask(
        task_id=task_id,
        title=f"Task {task_id}",
        description="desc",
        status=status,
        attempt_count=attempt_count,
        max_attempts=max_attempts,
    )


def _clean_run_record():
    """A clean run: both tasks DONE, review PASS."""
    state = SDLCState(
        spec_slug="fixture-spec",
        global_status=SDLCTaskStatus.DONE.value,
        tasks=[
            _task(1, SDLCTaskStatus.DONE, attempt_count=1),
            _task(2, SDLCTaskStatus.DONE, attempt_count=2),
        ],
        telemetry=SDLCTelemetry(total_attempts=3, tasks_passed=2, tasks_failed=0),
    )
    return {
        "nodes": {
            "LoadTaskStateNode": {"result": state.model_dump()},
            "UpdateTaskStatusNode": {"result": state.model_dump()},
            "ConsolidatedReviewNode": {
                "result": {
                    "verdict": SDLCReviewVerdict.PASS.value,
                    "summary": "Looks good.",
                    "issues": [],
                }
            },
        }
    }


def _bailed_run_record():
    """A MAJOR_BAIL run: one task exhausted attempts and was mutated to FAILED."""
    state = SDLCState(
        spec_slug="fixture-spec-bailed",
        global_status=SDLCTaskStatus.FAILED.value,
        tasks=[
            _task(1, SDLCTaskStatus.DONE, attempt_count=1),
            _task(2, SDLCTaskStatus.FAILED, attempt_count=3, max_attempts=3),
        ],
        telemetry=SDLCTelemetry(total_attempts=5, tasks_passed=1, tasks_failed=1),
    )
    return {
        "nodes": {
            "LoadTaskStateNode": {"result": state.model_dump()},
            "UpdateTaskStatusNode": {"result": state.model_dump()},
        }
    }


def _seed_events(session, records, workflow_type="SDLC_FLOW"):
    """Replace all ``events`` rows for ``workflow_type`` with ``records``.

    ``db_session`` (tests/conftest.py) is backed by a session-scoped
    in-memory engine shared across every test in the suite, and
    ``load_coding_records`` (Task 5) queries *all* rows for a workflow_type
    with no further scoping — so each test must clear prior rows first to
    keep its case_count/pass_rate assertions isolated from other tests.
    """
    session.query(Event).filter_by(workflow_type=workflow_type).delete(
        synchronize_session=False
    )
    for record in records:
        session.add(Event(workflow_type=workflow_type, data={}, task_context=record))
    session.commit()


def _fake_db_session_factory(session):
    """Build a fake ``db_session`` generator yielding ``session`` unclosed,
    matching scripts/index_brain.py's test pattern for lazily-imported
    module-level patches.
    """

    def _fake_db_session():
        yield session

    return _fake_db_session


class TestDryRun:
    def test_dry_run_lists_cases_without_executing_or_persisting(self, db_session, caplog):
        _seed_events(db_session, [_clean_run_record(), _bailed_run_record()])

        from database.eval_record import EvalRun

        # db_session's underlying engine is session-scoped and shared with
        # other test modules (tests/evals/test_runner.py etc.), which persist
        # their own fixture runs under other slice/model names — so assert no
        # *new* rows appeared, rather than an absolute count of zero.
        count_before = db_session.query(EvalRun).count()

        with (
            patch("database.session.db_session", _fake_db_session_factory(db_session)),
            caplog.at_level("INFO"),
        ):
            exit_code = main(["--slice", "coding", "--dry-run"])

        assert exit_code == 0
        assert "coding-0" in caplog.text
        assert "coding-1" in caplog.text

        assert db_session.query(EvalRun).count() == count_before


class TestRunAndTable:
    def test_run_prints_pass_rate_table_and_persists(self, db_session, capsys):
        _seed_events(db_session, [_clean_run_record(), _bailed_run_record()])
        model = f"model-{uuid.uuid4().hex[:8]}"

        with patch("database.session.db_session", _fake_db_session_factory(db_session)):
            exit_code = main(["--slice", "coding", "--models", model])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "domain" in out and "model" in out and "pass_rate" in out
        assert "coding" in out
        assert model in out

        from database.eval_record import EvalRun

        run = db_session.query(EvalRun).filter_by(slice_name="coding", model_name=model).one()
        assert run.case_count == 2
        assert run.passed_count == 1  # one clean (pass), one bailed (fail)
        assert run.pass_rate == pytest.approx(0.5)


class TestGate:
    def test_gate_exits_zero_on_keep(self, db_session, capsys):
        model = f"model-{uuid.uuid4().hex[:8]}"

        # First run: no baseline -> always keeps.
        _seed_events(db_session, [_clean_run_record()])
        with patch("database.session.db_session", _fake_db_session_factory(db_session)):
            exit_code = main(["--slice", "coding", "--models", model, "--gate"])

        assert exit_code == 0
        assert "keep" in capsys.readouterr().out.lower()

    def test_gate_exits_nonzero_on_revert(self, db_session, capsys):
        model = f"model-{uuid.uuid4().hex[:8]}"

        # Baseline: clean run (pass_rate 1.0).
        _seed_events(db_session, [_clean_run_record()])
        with patch("database.session.db_session", _fake_db_session_factory(db_session)):
            main(["--slice", "coding", "--models", model])

        # Candidate: bailed run (pass_rate 0.0) -> regression -> revert.
        _seed_events(db_session, [_bailed_run_record()])
        with patch("database.session.db_session", _fake_db_session_factory(db_session)):
            exit_code = main(["--slice", "coding", "--models", model, "--gate"])

        assert exit_code != 0
        assert "revert" in capsys.readouterr().out.lower()


class TestEmitRouting:
    def test_emit_routing_writes_quality_cost_and_floor_selection(self, db_session, tmp_path):
        model_cheap = f"model-cheap-{uuid.uuid4().hex[:8]}"
        model_good = f"model-good-{uuid.uuid4().hex[:8]}"
        routing_path = tmp_path / "routing.json"

        # Both models score against the same clean+bailed pair -> pass_rate 0.5 each,
        # so cost (duration proxy) breaks the tie for --quality-floor selection.
        _seed_events(db_session, [_clean_run_record(), _bailed_run_record()])
        with patch("database.session.db_session", _fake_db_session_factory(db_session)):
            exit_code = main(
                [
                    "--slice",
                    "coding",
                    "--models",
                    model_cheap,
                    model_good,
                    "--emit-routing",
                    str(routing_path),
                    "--quality-floor",
                    "0.0",
                ]
            )

        assert exit_code == 0
        assert routing_path.exists()
        routing = json.loads(routing_path.read_text(encoding="utf-8"))

        assert routing["slice"] == "coding"
        assert routing["domain"] == "coding"
        assert routing["quality_floor"] == 0.0
        assert set(routing["models"]) == {model_cheap, model_good}
        for entry in routing["models"].values():
            assert "quality" in entry and "cost" in entry
        assert routing["selected_model"] in {model_cheap, model_good}

    def test_emit_routing_quality_floor_excludes_low_quality_models(self, db_session, tmp_path):
        model_low = f"model-low-{uuid.uuid4().hex[:8]}"
        routing_path = tmp_path / "routing.json"

        # Only a bailed record -> pass_rate 0.0 for this model, below any positive floor.
        _seed_events(db_session, [_bailed_run_record()])
        with patch("database.session.db_session", _fake_db_session_factory(db_session)):
            main(
                [
                    "--slice",
                    "coding",
                    "--models",
                    model_low,
                    "--emit-routing",
                    str(routing_path),
                    "--quality-floor",
                    "0.5",
                ]
            )

        routing = json.loads(routing_path.read_text(encoding="utf-8"))
        assert routing["models"][model_low]["quality"] == pytest.approx(0.0)
        assert routing["selected_model"] is None
