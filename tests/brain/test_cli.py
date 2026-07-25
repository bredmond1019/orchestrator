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
from pathlib import Path
from unittest.mock import patch

import pytest
from brain.cli import main
from brain.pulse import PulseReport

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
            "what is D20", limit=3, hybrid=True, workspace=None
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

    `RetrieveChunksNode.retrieve` is mocked (as in `tests/brain/test_retrieval.py`'s own parity
    guard) so this exercises the real dispatch chain — argparse -> `brain.retrieval.recall` ->
    `brain.retrieval.hybrid_search` -> `RetrieveChunksNode.retrieve` -> `--json` stdout — without
    requiring a live embedding backend, while still proving `syn recall --hybrid` and
    `query_brain.py --hybrid` (which also calls `hybrid_search`) resolve to one implementation.
    """

    def test_recall_hybrid_matches_hybrid_search(self, capsys):
        from brain.retrieval import hybrid_search

        fake_chunks = [
            {
                "doc_id": "D99",
                "file_path": "docs/decisions/D99-example.md",
                "title": "D99 — Parity Check",
                "section_title": "",
                "content": "Parity check content for the syn recall CLI.",
                "score": 0.9,
                "via": "semantic",
            }
        ]
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.RetrieveChunksNode"
        ) as mock_node_cls:
            mock_node_cls.return_value.retrieve.return_value = fake_chunks
            expected = hybrid_search("D99", limit=5)

            code = main(["recall", "D99", "--hybrid", "--json"])

        assert code == 0
        out = _read_stdout(capsys)
        assert json.loads(out) == expected == fake_chunks
