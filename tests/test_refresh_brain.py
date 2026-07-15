"""Unit tests for scripts/refresh_brain.py.

Tests cover:
- main(): forwards --brain-path/--rebuild/--dry-run to index_brain.main, then
  calls refresh_edges (skipped entirely on --dry-run, which has no
  brain_edges equivalent)
- refresh_edges: shells out to `mev emit-graph --json`, parses the payload,
  and delegates to load_brain_edges.load_edges (mocked session/DB, no live DB)
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/ and app/ are importable, mirroring scripts/index_brain.py
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
APP_DIR = Path(__file__).resolve().parent.parent / "app"
for path in (SCRIPTS_DIR, APP_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from refresh_brain import main, refresh_edges  # noqa: E402

FAKE_PAYLOAD = {
    "version": "2",
    "nodes": [{"id": "orchestrator:D1", "doc_id": "D1", "scope": "orchestrator"}],
    "edges": [],
}


class TestMain:
    """main() sequencing: index_brain first, then brain_edges — unless --dry-run."""

    @patch("refresh_brain.refresh_edges")
    @patch("index_brain.main")
    def test_default_run_calls_both_steps(self, mock_index_main, mock_refresh_edges):
        mock_refresh_edges.return_value = 3
        main([])

        mock_index_main.assert_called_once_with([])
        mock_refresh_edges.assert_called_once()

    @patch("refresh_brain.refresh_edges")
    @patch("index_brain.main")
    def test_forwards_rebuild_and_brain_path_to_index_brain(
        self, mock_index_main, mock_refresh_edges
    ):
        mock_refresh_edges.return_value = 0
        main(["--brain-path", "/tmp/some-brain", "--rebuild"])

        mock_index_main.assert_called_once_with(
            ["--brain-path", "/tmp/some-brain", "--rebuild"]
        )
        # brain_path forwarded through to the edge-refresh step too
        called_path = mock_refresh_edges.call_args[0][0]
        assert str(called_path) == "/tmp/some-brain"

    @patch("refresh_brain.refresh_edges")
    @patch("index_brain.main")
    def test_dry_run_skips_edge_refresh_entirely(self, mock_index_main, mock_refresh_edges):
        main(["--dry-run"])

        mock_index_main.assert_called_once_with(["--dry-run"])
        mock_refresh_edges.assert_not_called()


class TestRefreshEdges:
    """refresh_edges: mev emit-graph subprocess -> load_edges, no live DB."""

    @patch("load_brain_edges.load_edges")
    @patch("database.session.db_session")
    @patch("refresh_brain.subprocess.run")
    def test_parses_mev_output_and_delegates_to_load_edges(
        self, mock_run, mock_db_session, mock_load_edges
    ):
        mock_run.return_value = MagicMock(stdout=json.dumps(FAKE_PAYLOAD))
        fake_session = MagicMock()
        fake_session.__enter__.return_value = fake_session
        mock_db_session.return_value = iter([fake_session])
        mock_load_edges.return_value = 7

        count = refresh_edges(Path("/tmp/brain-root"))

        mev_call_args = mock_run.call_args[0][0]
        assert mev_call_args == ["mev", "emit-graph", "--json", "/tmp/brain-root"]
        mock_load_edges.assert_called_once_with(FAKE_PAYLOAD, fake_session)
        assert count == 7

    @patch("load_brain_edges.load_edges")
    @patch("database.session.db_session")
    @patch("refresh_brain.subprocess.run")
    def test_propagates_mev_subprocess_failure(self, mock_run, mock_db_session, mock_load_edges):
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, ["mev", "emit-graph"])

        with pytest.raises(subprocess.CalledProcessError):
            refresh_edges(Path("/tmp/brain-root"))

        mock_load_edges.assert_not_called()
