"""Unit tests for scripts/refresh_brain.py — the thin shim over app.brain.ops.refresh.

Tests cover:
- main(): forwards --brain-path/--rebuild/--dry-run to app.brain.ops.refresh
  and logs the outcome (delegation asserted by patching `refresh_brain.refresh`)
- refresh_edges: re-exported from app.brain.ops for backward compatibility —
  still shells out to `mev emit-graph --json`, parses the payload, and
  delegates to load_brain_edges.load_edges (mocked session/DB, no live DB)
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
    """main() delegates to app.brain.ops.refresh with the parsed args."""

    @patch("refresh_brain.refresh")
    def test_default_run_delegates_to_ops_refresh(self, mock_refresh):
        mock_refresh.return_value = {"documents": {"dry_run": False}, "edges": {"loaded": 3}}
        main([])

        mock_refresh.assert_called_once_with(rebuild=False, dry_run=False, brain_path=None)

    @patch("refresh_brain.refresh")
    def test_forwards_rebuild_and_brain_path(self, mock_refresh):
        mock_refresh.return_value = {"documents": {"dry_run": False}, "edges": {"loaded": 0}}
        main(["--brain-path", "/tmp/some-brain", "--rebuild"])

        mock_refresh.assert_called_once_with(
            rebuild=True, dry_run=False, brain_path="/tmp/some-brain"
        )

    @patch("refresh_brain.refresh")
    def test_dry_run_forwarded_and_no_edge_logging_crash(self, mock_refresh):
        mock_refresh.return_value = {"documents": {"dry_run": True}, "edges": {"skipped": True}}
        main(["--dry-run"])

        mock_refresh.assert_called_once_with(rebuild=False, dry_run=True, brain_path=None)


class TestRefreshEdges:
    """refresh_edges (re-exported from app.brain.ops): mev subprocess -> load_edges, no live DB."""

    @patch("load_brain_edges.load_edges")
    @patch("database.session.db_session")
    @patch("brain.ops.subprocess.run")
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
    @patch("brain.ops.subprocess.run")
    def test_propagates_mev_subprocess_failure(self, mock_run, mock_db_session, mock_load_edges):
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, ["mev", "emit-graph"])

        with pytest.raises(subprocess.CalledProcessError):
            refresh_edges(Path("/tmp/brain-root"))

        mock_load_edges.assert_not_called()
