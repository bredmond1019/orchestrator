"""Tests for app/brain/ops.py — the Brain write/ops core (OR.N2 task 2).

Mocks `index_brain.main`, the `mev` subprocess, and `load_brain_edges.load_edges`
rather than requiring a live/Docker-gated DB — `stale()`'s DB read is exercised
against a MagicMock session built the same way `tests/test_index_brain.py`'s
incremental-skip tests do. Covers: `refresh()` step ordering + `--dry-run` skip,
`refresh_edges()` subprocess parsing + `MevUnavailableError`, `stale()`'s
content/structure axes (clean corpus -> zero drift; a changed file -> named;
pulse's `edges_empty_but_related_exists` -> `edges_stale`), `run_routine`
dispatch + `UnknownRoutineError`, and `embed_paths`/`ingest_dir`/`prune_paths`
argument forwarding.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from brain.ops import (
    MevUnavailableError,
    UnknownRoutineError,
    embed_paths,
    ingest_dir,
    prune_paths,
    refresh,
    refresh_edges,
    run_routine,
    stale,
)

FAKE_PAYLOAD = {
    "version": "2",
    "nodes": [{"id": "orchestrator:D1", "doc_id": "D1", "scope": "orchestrator"}],
    "edges": [],
}

_TEST_BRAIN_TOML = """\
[vocab]
layer = ["brain", "engine", "factory", "console", "surface", "infra", "business", "content", "meta"]
status = ["active", "draft", "deprecated", "superseded", "archived"]

[crawl]
skip_dirs = ["target", "node_modules", ".git", ".claude", ".agent", "planning/archive", "venv", ".venv"]

[[repos]]
slug = "brain"
tier = "_root"
repo_path = "."
status_file = "planning/status.md"
cache_doc = "README.md"
heading = "Company Brain"
"""


@pytest.fixture(autouse=True)
def _auto_brain_toml(tmp_path):
    """Make every test's `tmp_path` a valid brain root for `stale()`'s `_load_brain_config`."""
    (tmp_path / "brain.toml").write_text(_TEST_BRAIN_TOML, encoding="utf-8")


class TestEmbedPaths:
    """`embed_paths` forwards to `index_brain.main` with `--only-paths` (+ `--force`)."""

    @patch("index_brain.main")
    def test_forwards_only_paths(self, mock_main):
        result = embed_paths(["docs/a.md"])

        mock_main.assert_called_once_with(["--only-paths", "docs/a.md"])
        assert result == {"embedded": ["docs/a.md"], "forced": False}

    @patch("index_brain.main")
    def test_forwards_force_and_brain_path(self, mock_main):
        result = embed_paths(["docs/a.md"], force=True, brain_path="/tmp/brain")

        mock_main.assert_called_once_with(
            ["--only-paths", "docs/a.md", "--force", "--brain-path", "/tmp/brain"]
        )
        assert result["forced"] is True


class TestIngestDir:
    """`ingest_dir` expands a directory to its *.md files and reuses `embed_paths`."""

    @patch("brain.ops.embed_paths")
    def test_forwards_collected_files(self, mock_embed_paths, tmp_path):
        (tmp_path / "a.md").write_text("A", encoding="utf-8")
        (tmp_path / "b.md").write_text("B", encoding="utf-8")
        (tmp_path / "c.txt").write_text("C", encoding="utf-8")

        result = ingest_dir(str(tmp_path), force=True)

        called_files = mock_embed_paths.call_args[0][0]
        assert {p.split("/")[-1] for p in called_files} == {"a.md", "b.md"}
        assert mock_embed_paths.call_args.kwargs["force"] is True
        assert set(result["ingested"]) == set(called_files)

    def test_non_directory_raises(self, tmp_path):
        missing = tmp_path / "nope"

        with pytest.raises(NotADirectoryError):
            ingest_dir(str(missing))

    @patch("brain.ops.embed_paths")
    def test_empty_directory_is_a_noop(self, mock_embed_paths, tmp_path):
        result = ingest_dir(str(tmp_path))

        mock_embed_paths.assert_not_called()
        assert result == {"ingested": [], "forced": False}


class TestPrunePaths:
    """`prune_paths` forwards to `index_brain.main` with `--prune-paths`."""

    @patch("index_brain.main")
    def test_forwards_paths(self, mock_main):
        result = prune_paths(["docs/old.md", "docs/gone.md"])

        mock_main.assert_called_once_with(["--prune-paths", "docs/old.md", "docs/gone.md"])
        assert result == {"pruned": ["docs/old.md", "docs/gone.md"], "dry_run": False}

    @patch("index_brain.main")
    def test_forwards_dry_run_and_brain_path(self, mock_main):
        result = prune_paths(["docs/old.md"], dry_run=True, brain_path="/tmp/brain")

        mock_main.assert_called_once_with(
            ["--prune-paths", "docs/old.md", "--dry-run", "--brain-path", "/tmp/brain"]
        )
        assert result["dry_run"] is True


class TestRefreshEdges:
    """`refresh_edges` shells out to `mev emit-graph`, parses, delegates to `load_edges`."""

    @patch("load_brain_edges.load_edges")
    @patch("database.session.db_session")
    @patch("brain.ops.subprocess.run")
    def test_parses_mev_output_and_delegates_to_load_edges(
        self, mock_run, mock_db_session, mock_load_edges
    ):
        mock_run.return_value = MagicMock(stdout=json.dumps(FAKE_PAYLOAD))
        fake_session = MagicMock()
        fake_session.__enter__ = MagicMock(return_value=fake_session)
        fake_session.__exit__ = MagicMock(return_value=False)

        def fake_db_session():
            yield fake_session

        mock_db_session.side_effect = fake_db_session
        mock_load_edges.return_value = 3

        count = refresh_edges("/tmp/some-brain")

        mock_run.assert_called_once_with(
            ["mev", "emit-graph", "--json", "/tmp/some-brain"],
            capture_output=True,
            text=True,
            check=True,
        )
        mock_load_edges.assert_called_once_with(FAKE_PAYLOAD, fake_session)
        assert count == 3

    @patch("brain.ops.subprocess.run", side_effect=FileNotFoundError("no mev"))
    def test_missing_mev_binary_raises_typed_error(self, _mock_run):
        with pytest.raises(MevUnavailableError):
            refresh_edges("/tmp/some-brain")


class TestRefresh:
    """`refresh()` runs the content step then the edge step, in order; --dry-run skips edges."""

    @patch("brain.ops.refresh_edges")
    @patch("index_brain.main")
    def test_default_run_calls_both_steps_in_order(self, mock_index_main, mock_refresh_edges):
        parent = MagicMock()
        parent.attach_mock(mock_index_main, "index_main")
        parent.attach_mock(mock_refresh_edges, "refresh_edges")
        mock_refresh_edges.return_value = 5

        result = refresh()

        assert [c[0] for c in parent.mock_calls] == ["index_main", "refresh_edges"]
        mock_index_main.assert_called_once_with([])
        assert result == {"documents": {"dry_run": False}, "edges": {"loaded": 5}}

    @patch("brain.ops.refresh_edges")
    @patch("index_brain.main")
    def test_dry_run_skips_edge_step(self, mock_index_main, mock_refresh_edges):
        result = refresh(dry_run=True)

        mock_index_main.assert_called_once_with(["--dry-run"])
        mock_refresh_edges.assert_not_called()
        assert result == {"documents": {"dry_run": True}, "edges": {"skipped": True}}

    @patch("brain.ops.refresh_edges")
    @patch("index_brain.main")
    def test_forwards_rebuild_and_brain_path(self, mock_index_main, mock_refresh_edges):
        mock_refresh_edges.return_value = 0

        refresh(rebuild=True, brain_path="/tmp/some-brain")

        mock_index_main.assert_called_once_with(["--brain-path", "/tmp/some-brain", "--rebuild"])
        called_path = mock_refresh_edges.call_args[0][0]
        assert str(called_path) == "/tmp/some-brain"


class _FakePulseReport:
    def __init__(self, edges_empty_but_related_exists: bool) -> None:
        self.edges_empty_but_related_exists = edges_empty_but_related_exists


class TestStale:
    """`stale()`: content axis (mtime vs indexed_at, read-only) + structure axis (pulse reuse)."""

    def _make_mock_session(self, existing_indexed_at):
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        if existing_indexed_at is None:
            mock_query.first.return_value = None
        else:
            mock_doc = MagicMock()
            mock_doc.indexed_at = existing_indexed_at
            mock_query.first.return_value = mock_doc
        mock_session.query.return_value = mock_query
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        return mock_session

    @patch("brain.pulse.pulse")
    @patch("database.session.db_session")
    def test_untouched_corpus_reports_zero_drift(self, mock_db_session, mock_pulse, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "career.md").write_text("## Section\nContent.", encoding="utf-8")
        (tmp_path / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")

        future_indexed = datetime.now() + timedelta(hours=1)
        fake_session = self._make_mock_session(future_indexed)

        def fake_db_session():
            yield fake_session

        mock_db_session.side_effect = fake_db_session
        mock_pulse.return_value = _FakePulseReport(edges_empty_but_related_exists=False)

        result = stale(brain_path=str(tmp_path))

        assert result == {"changed_files": [], "edges_stale": False, "drift": False}

    @patch("brain.pulse.pulse")
    @patch("database.session.db_session")
    def test_changed_file_is_named(self, mock_db_session, mock_pulse, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "career.md").write_text("## Section\nContent.", encoding="utf-8")
        (tmp_path / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")

        old_indexed = datetime.now() - timedelta(hours=24)
        fake_session = self._make_mock_session(old_indexed)

        def fake_db_session():
            yield fake_session

        mock_db_session.side_effect = fake_db_session
        mock_pulse.return_value = _FakePulseReport(edges_empty_but_related_exists=False)

        result = stale(brain_path=str(tmp_path))

        assert result["changed_files"] == ["docs/career.md"]
        assert result["drift"] is True

    @patch("brain.pulse.pulse")
    @patch("database.session.db_session")
    def test_edges_stale_reflects_pulse_flag(self, mock_db_session, mock_pulse, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "career.md").write_text("## Section\nContent.", encoding="utf-8")
        (tmp_path / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")

        future_indexed = datetime.now() + timedelta(hours=1)
        fake_session = self._make_mock_session(future_indexed)

        def fake_db_session():
            yield fake_session

        mock_db_session.side_effect = fake_db_session
        mock_pulse.return_value = _FakePulseReport(edges_empty_but_related_exists=True)

        result = stale(brain_path=str(tmp_path))

        assert result["changed_files"] == []
        assert result["edges_stale"] is True
        assert result["drift"] is True


class TestRunRoutine:
    """`run_routine` dispatches over the `ROUTINES` registry; unknown names raise."""

    @patch("brain.ops.refresh")
    def test_dispatches_refresh(self, mock_refresh):
        mock_refresh.return_value = {"documents": {}, "edges": {}}

        result = run_routine("refresh")

        mock_refresh.assert_called_once_with()
        assert result == {"documents": {}, "edges": {}}

    @patch("brain.ops.stale")
    def test_dispatches_stale(self, mock_stale):
        mock_stale.return_value = {"changed_files": [], "edges_stale": False, "drift": False}

        result = run_routine("stale")

        mock_stale.assert_called_once_with()
        assert result["drift"] is False

    def test_unknown_name_raises(self):
        with pytest.raises(UnknownRoutineError):
            run_routine("nope")
