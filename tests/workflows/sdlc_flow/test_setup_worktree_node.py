"""Unit tests for SetupWorktreeNode."""

from unittest.mock import MagicMock, patch

import pytest
from core.task import TaskContext
from schemas.sdlc_schema import SDLCFlowEventSchema
from workflows.sdlc_flow_workflow_nodes.setup_worktree_node import SetupWorktreeNode


def _make_ctx(**overrides) -> TaskContext:
    defaults = {"spec_slug": "test-spec"}
    defaults.update(overrides)
    return TaskContext(event=SDLCFlowEventSchema(**defaults))


class TestSetupWorktreeNode:
    def test_happy_path_creates_worktree(self):
        ctx = _make_ctx()
        with (
            patch(
                "workflows.sdlc_flow_workflow_nodes.setup_worktree_node.subprocess.run"
            ) as mock_run,
            patch(
                "workflows.sdlc_flow_workflow_nodes.setup_worktree_node.Path.exists",
                return_value=False,
            ),
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            node = SetupWorktreeNode()
            result = node.process(ctx)

        assert result is ctx
        output = ctx.get_node_output("SetupWorktreeNode")
        assert output["result"]["worktree_path"] == "trees/sdlc/test-spec"
        assert output["result"]["branch_name"] == "sdlc/test-spec"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[:3] == ["git", "worktree", "add"]
        assert "sdlc/test-spec" in args

    def test_resume_skips_creation(self):
        ctx = _make_ctx(resume=True)
        with (
            patch(
                "workflows.sdlc_flow_workflow_nodes.setup_worktree_node.subprocess.run"
            ) as mock_run,
            patch(
                "workflows.sdlc_flow_workflow_nodes.setup_worktree_node.Path.exists",
                return_value=True,
            ),
        ):
            node = SetupWorktreeNode()
            node.process(ctx)

        mock_run.assert_not_called()
        output = ctx.get_node_output("SetupWorktreeNode")
        assert output["result"]["worktree_path"] == "trees/sdlc/test-spec"
        assert output["result"]["branch_name"] == "sdlc/test-spec"

    def test_custom_branch_name(self):
        ctx = _make_ctx(branch_name="my-branch")
        with (
            patch(
                "workflows.sdlc_flow_workflow_nodes.setup_worktree_node.subprocess.run"
            ) as mock_run,
            patch(
                "workflows.sdlc_flow_workflow_nodes.setup_worktree_node.Path.exists",
                return_value=False,
            ),
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            node = SetupWorktreeNode()
            node.process(ctx)

        output = ctx.get_node_output("SetupWorktreeNode")
        assert output["result"]["worktree_path"] == "trees/my-branch"
        assert output["result"]["branch_name"] == "my-branch"

    def test_failure_cleans_up(self):
        ctx = _make_ctx()
        with (
            patch(
                "workflows.sdlc_flow_workflow_nodes.setup_worktree_node.subprocess.run"
            ) as mock_run,
            patch(
                "workflows.sdlc_flow_workflow_nodes.setup_worktree_node.Path.exists",
                return_value=False,
            ),
        ):
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="error"),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            node = SetupWorktreeNode()
            with pytest.raises(RuntimeError, match="git worktree add failed"):
                node.process(ctx)

        assert mock_run.call_count == 2
        cleanup_args = mock_run.call_args_list[1][0][0]
        assert cleanup_args[:3] == ["git", "worktree", "remove"]
