"""Unit tests for TestTaskNode."""

import json
from unittest.mock import MagicMock, patch

from core.task import TaskContext
from schemas.sdlc_schema import SDLCFlowEventSchema
from workflows.sdlc_flow_workflow_nodes.test_task_node import TestTaskNode, TestTaskResult


def _make_ctx(worktree_path: str) -> TaskContext:
    ctx = TaskContext(event=SDLCFlowEventSchema(spec_slug="test-spec"))
    ctx.nodes["SetupWorktreeNode"] = {
        "result": {"worktree_path": worktree_path, "branch_name": "sdlc/test-spec"}
    }
    return ctx


def _write_harness(tmp_path, checks: list[dict]) -> None:
    harness_dir = tmp_path / "planning"
    harness_dir.mkdir(parents=True, exist_ok=True)
    harness_path = harness_dir / "harness.json"
    harness_path.write_text(
        json.dumps({"validation": {"checks": checks}}), encoding="utf-8"
    )


class TestTestTaskNode:
    def test_all_checks_pass(self, tmp_path):
        _write_harness(
            tmp_path,
            [
                {"name": "check-a", "kind": "command", "command": "true", "gates": True},
                {"name": "check-b", "kind": "command", "command": "true", "gates": True},
            ],
        )
        ctx = _make_ctx(str(tmp_path))

        with patch(
            "workflows.sdlc_flow_workflow_nodes.test_task_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            node = TestTaskNode()
            result = node.process(ctx)

        assert result is ctx
        output = ctx.get_node_output("TestTaskNode")["result"]
        parsed = TestTaskResult.model_validate(output)
        assert parsed.all_passed is True
        assert len(parsed.check_results) == 2
        assert mock_run.call_count == 2

    def test_command_failure(self, tmp_path):
        _write_harness(
            tmp_path,
            [
                {"name": "check-a", "kind": "command", "command": "true", "gates": True},
                {"name": "check-b", "kind": "command", "command": "false", "gates": True},
            ],
        )
        ctx = _make_ctx(str(tmp_path))

        def _side_effect(command, **_kwargs):
            returncode = 1 if command == "false" else 0
            return MagicMock(returncode=returncode, stdout="", stderr="boom")

        with patch(
            "workflows.sdlc_flow_workflow_nodes.test_task_node.subprocess.run",
            side_effect=_side_effect,
        ):
            node = TestTaskNode()
            node.process(ctx)

        output = ctx.get_node_output("TestTaskNode")["result"]
        parsed = TestTaskResult.model_validate(output)
        assert parsed.all_passed is False
        failed = [cr for cr in parsed.check_results if cr.name == "check-b"]
        assert failed[0].passed is False
        assert "check-b" in parsed.failure_summary

    def test_forbidden_pattern_scan_catches_violation(self, tmp_path):
        _write_harness(
            tmp_path,
            [
                {
                    "name": "standing-rules",
                    "kind": "forbidden-pattern-scan",
                    "gates": True,
                    "rules": [
                        {
                            "id": "bad-pattern",
                            "pattern": "TODO",
                            "paths": "--include='*.py' app/",
                        }
                    ],
                }
            ],
        )
        ctx = _make_ctx(str(tmp_path))

        with patch(
            "workflows.sdlc_flow_workflow_nodes.test_task_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="app/foo.py:1:TODO fix me\n", stderr=""
            )
            node = TestTaskNode()
            node.process(ctx)

        output = ctx.get_node_output("TestTaskNode")["result"]
        parsed = TestTaskResult.model_validate(output)
        assert parsed.all_passed is False
        assert parsed.check_results[0].passed is False

    def test_forbidden_pattern_scan_allowlist_passes(self, tmp_path):
        _write_harness(
            tmp_path,
            [
                {
                    "name": "standing-rules",
                    "kind": "forbidden-pattern-scan",
                    "gates": True,
                    "rules": [
                        {
                            "id": "bad-pattern",
                            "pattern": "TODO",
                            "paths": "--include='*.py' app/",
                            "allowlistPattern": "fix me",
                        }
                    ],
                }
            ],
        )
        ctx = _make_ctx(str(tmp_path))

        with patch(
            "workflows.sdlc_flow_workflow_nodes.test_task_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="app/foo.py:1:TODO fix me\n", stderr=""
            )
            node = TestTaskNode()
            node.process(ctx)

        output = ctx.get_node_output("TestTaskNode")["result"]
        parsed = TestTaskResult.model_validate(output)
        assert parsed.all_passed is True
        assert parsed.check_results[0].passed is True

    def test_count_delta_decrease_fails(self, tmp_path):
        _write_harness(
            tmp_path,
            [
                {
                    "name": "pytest-count",
                    "kind": "count-delta",
                    "gates": True,
                    "command": "pytest --collect-only -q",
                    "countPattern": r"[0-9]+ tests? collected",
                    "failOn": "decrease",
                    "baseline": 10,
                }
            ],
        )
        ctx = _make_ctx(str(tmp_path))

        with patch(
            "workflows.sdlc_flow_workflow_nodes.test_task_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="5 tests collected\n", stderr=""
            )
            node = TestTaskNode()
            node.process(ctx)

        output = ctx.get_node_output("TestTaskNode")["result"]
        parsed = TestTaskResult.model_validate(output)
        assert parsed.all_passed is False
        assert parsed.check_results[0].passed is False

    def test_count_delta_increase_passes(self, tmp_path):
        _write_harness(
            tmp_path,
            [
                {
                    "name": "pytest-count",
                    "kind": "count-delta",
                    "gates": True,
                    "command": "pytest --collect-only -q",
                    "countPattern": r"[0-9]+ tests? collected",
                    "failOn": "decrease",
                    "baseline": 10,
                }
            ],
        )
        ctx = _make_ctx(str(tmp_path))

        with patch(
            "workflows.sdlc_flow_workflow_nodes.test_task_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="15 tests collected\n", stderr=""
            )
            node = TestTaskNode()
            node.process(ctx)

        output = ctx.get_node_output("TestTaskNode")["result"]
        parsed = TestTaskResult.model_validate(output)
        assert parsed.all_passed is True
        assert parsed.check_results[0].passed is True

    def test_missing_harness_defaults_pass(self, tmp_path):
        ctx = _make_ctx(str(tmp_path))
        node = TestTaskNode()
        node.process(ctx)

        output = ctx.get_node_output("TestTaskNode")["result"]
        parsed = TestTaskResult.model_validate(output)
        assert parsed.all_passed is True
        assert parsed.check_results == []

    def test_disabled_check_skipped(self, tmp_path):
        _write_harness(
            tmp_path,
            [
                {
                    "name": "skip-me",
                    "kind": "command",
                    "command": "false",
                    "gates": True,
                    "enabled": False,
                },
                {"name": "check-a", "kind": "command", "command": "true", "gates": True},
            ],
        )
        ctx = _make_ctx(str(tmp_path))

        with patch(
            "workflows.sdlc_flow_workflow_nodes.test_task_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            node = TestTaskNode()
            node.process(ctx)

        output = ctx.get_node_output("TestTaskNode")["result"]
        parsed = TestTaskResult.model_validate(output)
        names = [cr.name for cr in parsed.check_results]
        assert "skip-me" not in names
        assert mock_run.call_count == 1

    def test_warning_scan_non_gating(self, tmp_path):
        _write_harness(
            tmp_path,
            [
                {
                    "name": "app-import",
                    "kind": "warning-scan",
                    "gates": False,
                    "command": "python -c 'import main'",
                    "warningPatterns": ["UserWarning"],
                }
            ],
        )
        ctx = _make_ctx(str(tmp_path))

        with patch(
            "workflows.sdlc_flow_workflow_nodes.test_task_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="UserWarning: field shadows\n", stderr=""
            )
            node = TestTaskNode()
            node.process(ctx)

        output = ctx.get_node_output("TestTaskNode")["result"]
        parsed = TestTaskResult.model_validate(output)
        assert parsed.all_passed is True
        assert parsed.check_results[0].passed is True
