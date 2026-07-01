"""Unit tests for the Task 8 completion nodes.

Covers:
- ConsolidatedReviewNode: mocked agent verdicts, git diff read via mocked
  subprocess.
- ReviewRouterNode / _ReviewVerdictRouter: routes PASS -> UpdateTaskStatusNode,
  minor FAIL/PARTIAL -> ImplementTaskNode, structural FAIL -> WrapUpNode.
- PatchDocsNode: mocked agent, verifies output shape.
- WrapUpNode: mocked agent, verifies output shape.
- PullRequestNode: mocked subprocess for git push + gh pr create; auto_pr=False
  skip path; asserts no auto-merge is ever attempted (D25 guard).

Agents are mocked — no real pydantic-ai Agent is constructed, so these tests
need no API key or network connection.
"""

from unittest.mock import MagicMock, patch

from core.task import NodeRun, NodeStatus, TaskContext
from schemas.sdlc_schema import SDLCFlowEventSchema, SDLCState, SDLCTask
from workflows.sdlc_flow_workflow_nodes.consolidated_review_node import (
    ConsolidatedReviewNode,
)
from workflows.sdlc_flow_workflow_nodes.implement_task_node import ImplementTaskNode
from workflows.sdlc_flow_workflow_nodes.patch_docs_node import PatchDocsNode
from workflows.sdlc_flow_workflow_nodes.pull_request_node import PullRequestNode
from workflows.sdlc_flow_workflow_nodes.review_router_node import (
    ReviewRouterNode,
    _ReviewVerdictRouter,
)
from workflows.sdlc_flow_workflow_nodes.update_task_status_node import (
    UpdateTaskStatusNode,
)
from workflows.sdlc_flow_workflow_nodes.wrap_up_node import WrapUpNode


def _make_agent_node(node_cls):
    """Build an AgentNode without constructing a real Agent / model."""
    node = node_cls.__new__(node_cls)
    node.agent = MagicMock()
    return node


def _result_for(output) -> MagicMock:
    result = MagicMock()
    result.output = output
    result.usage.return_value = MagicMock(input_tokens=10, output_tokens=20)
    return result


def _seed_run(ctx: TaskContext, node) -> None:
    ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)


def _make_event(**overrides) -> SDLCFlowEventSchema:
    defaults = {"spec_slug": "test-spec"}
    defaults.update(overrides)
    return SDLCFlowEventSchema(**defaults)


# ---------------------------------------------------------------------------
# ConsolidatedReviewNode
# ---------------------------------------------------------------------------


class TestConsolidatedReviewNode:
    def _make_ctx(self) -> TaskContext:
        ctx = TaskContext(event=_make_event())
        ctx.nodes["SetupWorktreeNode"] = {
            "result": {"worktree_path": "trees/sdlc/test-spec", "branch_name": "sdlc/test-spec"}
        }
        ctx.nodes["TaskQueueRouterNode"] = {
            "result": {
                "current_task_id": 1,
                "title": "Add feature",
                "acceptance_criteria": ["Does the thing"],
            }
        }
        return ctx

    def test_pass_verdict(self):
        node = _make_agent_node(ConsolidatedReviewNode)
        output = ConsolidatedReviewNode.OutputType(
            verdict="PASS", summary="Meets all criteria.", issues=[]
        )
        node.agent.run_sync.return_value = _result_for(output)
        ctx = self._make_ctx()
        _seed_run(ctx, node)

        with patch(
            "workflows.sdlc_flow_workflow_nodes.consolidated_review_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="diff --git a b", stderr="")
            node.process(ctx)

        stored = ctx.nodes["ConsolidatedReviewNode"]["result"]
        assert stored["verdict"] == "PASS"
        assert stored["issues"] == []

    def test_fail_verdict(self):
        node = _make_agent_node(ConsolidatedReviewNode)
        output = ConsolidatedReviewNode.OutputType(
            verdict="FAIL", summary="Missing tests.", issues=["No test coverage"]
        )
        node.agent.run_sync.return_value = _result_for(output)
        ctx = self._make_ctx()
        _seed_run(ctx, node)

        with patch(
            "workflows.sdlc_flow_workflow_nodes.consolidated_review_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            node.process(ctx)

        stored = ctx.nodes["ConsolidatedReviewNode"]["result"]
        assert stored["verdict"] == "FAIL"
        assert stored["issues"] == ["No test coverage"]

    def test_reads_git_diff(self):
        node = _make_agent_node(ConsolidatedReviewNode)
        output = ConsolidatedReviewNode.OutputType(verdict="PASS", summary="ok", issues=[])
        node.agent.run_sync.return_value = _result_for(output)
        ctx = self._make_ctx()
        _seed_run(ctx, node)

        with patch(
            "workflows.sdlc_flow_workflow_nodes.consolidated_review_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="diff --git a/x.py b/x.py", stderr=""
            )
            node.process(ctx)

        args, kwargs = mock_run.call_args
        assert args[0][:2] == ["git", "diff"]
        assert kwargs["cwd"] == "trees/sdlc/test-spec"
        prompt_arg = node.agent.run_sync.call_args
        assert "diff --git a/x.py b/x.py" in str(prompt_arg)


# ---------------------------------------------------------------------------
# ReviewRouterNode / _ReviewVerdictRouter
# ---------------------------------------------------------------------------


class TestReviewRouterNode:
    def _ctx_with_verdict(self, verdict: str, issues: list[str] | None = None) -> TaskContext:
        ctx = TaskContext(event=_make_event())
        ctx.nodes["ConsolidatedReviewNode"] = {
            "result": {"verdict": verdict, "summary": "n/a", "issues": issues or []}
        }
        return ctx

    def test_routes_to_update_on_pass(self):
        ctx = self._ctx_with_verdict("PASS")
        next_node = _ReviewVerdictRouter().determine_next_node(ctx)
        assert isinstance(next_node, UpdateTaskStatusNode)

    def test_routes_to_implement_on_fail_minor(self):
        ctx = self._ctx_with_verdict("FAIL", issues=["one small issue"])
        next_node = _ReviewVerdictRouter().determine_next_node(ctx)
        assert isinstance(next_node, ImplementTaskNode)

    def test_routes_to_implement_on_partial(self):
        ctx = self._ctx_with_verdict("PARTIAL", issues=["needs a tweak"])
        next_node = _ReviewVerdictRouter().determine_next_node(ctx)
        assert isinstance(next_node, ImplementTaskNode)

    def test_routes_to_wrapup_on_structural_fail(self, monkeypatch):
        # WrapUpNode is a real AgentNode — its constructor needs an API key
        # to build the underlying pydantic-ai Agent, even though no model
        # call happens in this routing test.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        ctx = self._ctx_with_verdict(
            "FAIL", issues=[f"issue {i}" for i in range(10)]
        )
        next_node = _ReviewVerdictRouter().determine_next_node(ctx)
        assert isinstance(next_node, WrapUpNode)

    def test_no_route_when_result_missing(self):
        ctx = TaskContext(event=_make_event())
        ctx.nodes["ConsolidatedReviewNode"] = {"result": None}
        next_node = _ReviewVerdictRouter().determine_next_node(ctx)
        assert next_node is None

    def test_router_process_records_next_node(self):
        ctx = self._ctx_with_verdict("PASS")
        router = ReviewRouterNode()
        router.process(ctx)

        assert "ReviewRouterNode" in ctx.nodes
        assert ctx.nodes["ReviewRouterNode"]["next_node"] == "UpdateTaskStatusNode"

    def test_router_has_no_fallback(self):
        router = ReviewRouterNode()
        assert router.fallback is None


# ---------------------------------------------------------------------------
# PatchDocsNode
# ---------------------------------------------------------------------------


class TestPatchDocsNode:
    def test_produces_summary(self):
        node = _make_agent_node(PatchDocsNode)
        output = PatchDocsNode.OutputType(
            summary="Updated references in two files.",
            files_patched=["docs/api-reference.md"],
        )
        node.agent.run_sync.return_value = _result_for(output)

        ctx = TaskContext(event=_make_event())
        ctx.nodes["ImplementTaskNode"] = {
            "result": {
                "summary": "Added foo()",
                "modified_files": ["app/foo.py"],
                "tests_added": ["tests/test_foo.py"],
            }
        }
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes["PatchDocsNode"]["result"]
        assert stored["summary"] == "Updated references in two files."
        assert stored["files_patched"] == ["docs/api-reference.md"]

    def test_no_modified_files_when_implement_task_not_run(self):
        node = _make_agent_node(PatchDocsNode)
        output = PatchDocsNode.OutputType(summary="Nothing to patch.", files_patched=[])
        node.agent.run_sync.return_value = _result_for(output)

        ctx = TaskContext(event=_make_event())
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes["PatchDocsNode"]["result"]
        assert stored["files_patched"] == []


# ---------------------------------------------------------------------------
# WrapUpNode
# ---------------------------------------------------------------------------


class TestWrapUpNode:
    def test_produces_log_entry_and_report(self):
        node = _make_agent_node(WrapUpNode)
        output = WrapUpNode.OutputType(
            log_entry="## 2026-07-01\nCompleted test-spec.",
            report="# Report\nAll tasks passed.",
            status_suggestion="Mark Block 8 done.",
        )
        node.agent.run_sync.return_value = _result_for(output)

        state = SDLCState(
            spec_slug="test-spec",
            tasks=[SDLCTask(task_id=1, title="t", description="d")],
        )
        state.telemetry.tasks_passed = 1
        state.telemetry.total_attempts = 2

        ctx = TaskContext(event=_make_event())
        ctx.nodes["LoadTaskStateNode"] = {"result": state.model_dump()}
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes["WrapUpNode"]["result"]
        assert stored["log_entry"] == "## 2026-07-01\nCompleted test-spec."
        assert stored["report"] == "# Report\nAll tasks passed."
        assert stored["status_suggestion"] == "Mark Block 8 done."

    def test_prefers_update_task_status_state_over_load(self):
        node = _make_agent_node(WrapUpNode)
        output = WrapUpNode.OutputType(
            log_entry="entry", report="report", status_suggestion="suggestion"
        )
        node.agent.run_sync.return_value = _result_for(output)

        stale_state = SDLCState(spec_slug="stale-spec", tasks=[])
        fresh_state = SDLCState(spec_slug="test-spec", tasks=[])

        ctx = TaskContext(event=_make_event())
        ctx.nodes["LoadTaskStateNode"] = {"result": stale_state.model_dump()}
        ctx.nodes["UpdateTaskStatusNode"] = {"result": fresh_state.model_dump()}
        _seed_run(ctx, node)

        node.process(ctx)

        # The rendered prompt should reference the fresher spec_slug.
        assert "test-spec" in str(node.agent.run_sync.call_args)


# ---------------------------------------------------------------------------
# PullRequestNode
# ---------------------------------------------------------------------------


class TestPullRequestNode:
    def _make_ctx(self, auto_pr: bool = True) -> TaskContext:
        ctx = TaskContext(event=_make_event(auto_pr=auto_pr))
        ctx.nodes["SetupWorktreeNode"] = {
            "result": {"worktree_path": "trees/sdlc/test-spec", "branch_name": "sdlc/test-spec"}
        }
        return ctx

    def test_happy_path_creates_pr(self):
        ctx = self._make_ctx(auto_pr=True)
        node = PullRequestNode()

        with patch(
            "workflows.sdlc_flow_workflow_nodes.pull_request_node.subprocess.run"
        ) as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),  # git push
                MagicMock(
                    returncode=0,
                    stdout="https://github.com/org/repo/pull/42\n",
                    stderr="",
                ),  # gh pr create
            ]
            node.process(ctx)

        stored = ctx.nodes["PullRequestNode"]["result"]
        assert stored["pr_url"] == "https://github.com/org/repo/pull/42"
        assert stored["skipped"] is False
        assert mock_run.call_count == 2

        push_args = mock_run.call_args_list[0][0][0]
        assert push_args == ["git", "push", "origin", "sdlc/test-spec"]

        pr_args = mock_run.call_args_list[1][0][0]
        assert pr_args[:3] == ["gh", "pr", "create"]

    def test_auto_pr_false_skips(self):
        ctx = self._make_ctx(auto_pr=False)
        node = PullRequestNode()

        with patch(
            "workflows.sdlc_flow_workflow_nodes.pull_request_node.subprocess.run"
        ) as mock_run:
            node.process(ctx)

        mock_run.assert_not_called()
        stored = ctx.nodes["PullRequestNode"]["result"]
        assert stored["pr_url"] is None
        assert stored["skipped"] is True

    def test_no_auto_merge(self):
        ctx = self._make_ctx(auto_pr=True)
        node = PullRequestNode()

        with patch(
            "workflows.sdlc_flow_workflow_nodes.pull_request_node.subprocess.run"
        ) as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="https://github.com/org/repo/pull/1\n", stderr=""),
            ]
            node.process(ctx)

        for call in mock_run.call_args_list:
            args = call[0][0]
            assert "merge" not in args

    def test_push_failure_raises(self):
        ctx = self._make_ctx(auto_pr=True)
        node = PullRequestNode()

        with patch(
            "workflows.sdlc_flow_workflow_nodes.pull_request_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="push failed")
            try:
                node.process(ctx)
                raised = False
            except RuntimeError:
                raised = True
        assert raised
