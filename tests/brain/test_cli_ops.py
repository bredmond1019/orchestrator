"""Tests for app/brain/cli.py's OR.N2 write/ops subcommands (task 3).

Dispatches `embed`/`ingest`/`refresh`/`stale`/`routine` via `main([...])` with
`app.brain.ops` patched, asserting argument wiring, that `--json` output
parses as JSON and is the sole stdout payload, deterministic exit codes
(`stale --assert-clean` non-zero on drift, 0 when clean; unknown `routine`
name non-zero without a traceback), and that `--force` forwards correctly.
"""

import json
from unittest.mock import patch

from brain.cli import main
from brain.ops import UnknownRoutineError


def _read_stdout(capsys) -> str:
    return capsys.readouterr().out


class TestEmbedDispatch:
    """`syn embed` wires argparse args to `brain.ops.embed_paths`."""

    def test_embed_json_forwards_force_and_emits_sole_payload(self, capsys):
        fake_result = {"embedded": ["a.md"], "forced": True}
        with patch("brain.ops.embed_paths", return_value=fake_result) as mock_embed:
            code = main(["embed", "a.md", "--force", "--json"])

        assert code == 0
        mock_embed.assert_called_once_with(["a.md"], force=True, brain_path=None)
        out = _read_stdout(capsys)
        assert json.loads(out) == fake_result

    def test_embed_without_force_defaults_false(self, capsys):
        fake_result = {"embedded": ["a.md"], "forced": False}
        with patch("brain.ops.embed_paths", return_value=fake_result) as mock_embed:
            code = main(["embed", "a.md", "--json"])

        assert code == 0
        mock_embed.assert_called_once_with(["a.md"], force=False, brain_path=None)

    def test_embed_human_mode_does_not_emit_raw_json(self, capsys):
        fake_result = {"embedded": ["a.md"], "forced": False}
        with patch("brain.ops.embed_paths", return_value=fake_result):
            code = main(["embed", "a.md"])

        assert code == 0
        out = _read_stdout(capsys)
        assert "a.md" in out

    def test_embed_error_returns_nonzero_no_traceback(self, capsys):
        with patch("brain.ops.embed_paths", side_effect=RuntimeError("boom")):
            code = main(["embed", "a.md", "--json"])

        assert code != 0
        payload = json.loads(_read_stdout(capsys))
        assert "error" in payload


class TestIngestDispatch:
    """`syn ingest --dir` wires argparse args to `brain.ops.ingest_dir`."""

    def test_ingest_json_forwards_directory_and_force(self, capsys):
        fake_result = {"ingested": ["d/a.md", "d/b.md"], "forced": False}
        with patch("brain.ops.ingest_dir", return_value=fake_result) as mock_ingest:
            code = main(["ingest", "--dir", "d", "--json"])

        assert code == 0
        mock_ingest.assert_called_once_with("d", force=False, brain_path=None)
        out = _read_stdout(capsys)
        assert json.loads(out) == fake_result

    def test_ingest_force_forwards_true(self, capsys):
        fake_result = {"ingested": ["d/a.md"], "forced": True}
        with patch("brain.ops.ingest_dir", return_value=fake_result) as mock_ingest:
            code = main(["ingest", "--dir", "d", "--force", "--json"])

        assert code == 0
        mock_ingest.assert_called_once_with("d", force=True, brain_path=None)

    def test_ingest_error_returns_nonzero_no_traceback(self, capsys):
        with patch("brain.ops.ingest_dir", side_effect=NotADirectoryError("nope")):
            code = main(["ingest", "--dir", "d", "--json"])

        assert code != 0
        payload = json.loads(_read_stdout(capsys))
        assert "error" in payload


class TestRefreshDispatch:
    """`syn refresh` wires argparse args to `brain.ops.refresh`."""

    def test_refresh_json_forwards_rebuild_and_dry_run(self, capsys):
        fake_result = {"documents": {"dry_run": False}, "edges": {"loaded": 3}}
        with patch("brain.ops.refresh", return_value=fake_result) as mock_refresh:
            code = main(["refresh", "--rebuild", "--json"])

        assert code == 0
        mock_refresh.assert_called_once_with(rebuild=True, dry_run=False, brain_path=None)
        out = _read_stdout(capsys)
        assert json.loads(out) == fake_result

    def test_refresh_dry_run_forwards_true(self, capsys):
        fake_result = {"documents": {"dry_run": True}, "edges": {"skipped": True}}
        with patch("brain.ops.refresh", return_value=fake_result) as mock_refresh:
            code = main(["refresh", "--dry-run", "--json"])

        assert code == 0
        mock_refresh.assert_called_once_with(rebuild=False, dry_run=True, brain_path=None)


class TestStaleDispatch:
    """`syn stale` wires to `brain.ops.stale`; `--assert-clean` gates exit code on drift."""

    def test_stale_json_reports_clean_and_exits_zero(self, capsys):
        fake_result = {"changed_files": [], "edges_stale": False, "drift": False}
        with patch("brain.ops.stale", return_value=fake_result) as mock_stale:
            code = main(["stale", "--json"])

        assert code == 0
        mock_stale.assert_called_once_with(brain_path=None)
        out = _read_stdout(capsys)
        assert json.loads(out) == fake_result

    def test_stale_assert_clean_exits_nonzero_on_drift(self, capsys):
        fake_result = {"changed_files": ["docs/x.md"], "edges_stale": False, "drift": True}
        with patch("brain.ops.stale", return_value=fake_result):
            code = main(["stale", "--assert-clean", "--json"])

        assert code != 0

    def test_stale_assert_clean_exits_zero_when_clean(self, capsys):
        fake_result = {"changed_files": [], "edges_stale": False, "drift": False}
        with patch("brain.ops.stale", return_value=fake_result):
            code = main(["stale", "--assert-clean", "--json"])

        assert code == 0

    def test_stale_without_assert_clean_exits_zero_even_with_drift(self, capsys):
        fake_result = {"changed_files": ["docs/x.md"], "edges_stale": True, "drift": True}
        with patch("brain.ops.stale", return_value=fake_result):
            code = main(["stale", "--json"])

        assert code == 0


class TestRoutineDispatch:
    """`syn routine <name>` wires to `brain.ops.run_routine`."""

    def test_routine_dispatches_known_name(self, capsys):
        fake_result = {"documents": {"dry_run": False}, "edges": {"loaded": 0}}
        with patch("brain.ops.run_routine", return_value=fake_result) as mock_run:
            code = main(["routine", "refresh", "--json"])

        assert code == 0
        mock_run.assert_called_once_with("refresh")
        out = _read_stdout(capsys)
        assert json.loads(out) == fake_result

    def test_routine_unknown_name_exits_nonzero_no_traceback(self, capsys):
        with patch("brain.ops.run_routine", side_effect=UnknownRoutineError("nope")):
            code = main(["routine", "nope", "--json"])

        assert code != 0
        payload = json.loads(_read_stdout(capsys))
        assert "error" in payload
