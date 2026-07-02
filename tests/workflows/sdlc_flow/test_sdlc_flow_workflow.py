"""Integration tests for the assembled ``SDLCFlowWorkflow`` (Task 9).

Two layers:

* **Structure** — ``WorkflowValidator`` accepts the schema (acyclic declared
  graph despite the runtime retry/next-task loops), the start node and full
  16-node set are correct, and every router carries ``is_router=True``.
  Registration in both ``WorkflowRegistry`` and ``SCHEMA_MAP`` is verified
  (standing rule 6).
* **E2E smoke test** — the full DAG is run end-to-end with every ``AgentNode``
  mocked (no API key, no network, no real Claude Code invocation) and every
  git/subprocess call mocked. Covers the happy path (single task, first-try
  pass), the ``TriageTaskNode`` retry loop (fails once, RETRYABLE, then
  passes), the ``MAJOR_BAIL`` path (skips review/update-status, straight to
  wrap-up), and ``auto_pr=False`` (``PullRequestNode`` no-ops).

Filesystem state (``tasks.json`` / ``sdlc-flow-state.json``) is exercised for
real against a ``tmp_path`` "worktree" — only the git/subprocess boundary and
the LLM agents are mocked, so this test also proves ``LoadTaskStateNode`` /
``SaveStateNode`` / ``TaskQueueRouterNode`` interoperate correctly on real
JSON, not just mocked dicts.
"""

import json
from unittest.mock import MagicMock, patch

from api.schema_registry import SCHEMA_MAP
from core.nodes.agent import AgentNode
from core.task import NodeStatus, TaskContext
from core.validate import WorkflowValidator
from schemas.sdlc_schema import SDLCFlowEventSchema
from workflows.sdlc_flow_workflow import SDLCFlowWorkflow
from workflows.sdlc_flow_workflow_nodes.consolidated_review_node import (
    ConsolidatedReviewNode,
)
from workflows.sdlc_flow_workflow_nodes.generate_tasks_node import (
    GeneratedTask,
    GenerateTasksNode,
)
from workflows.sdlc_flow_workflow_nodes.implement_task_node import ImplementTaskNode
from workflows.sdlc_flow_workflow_nodes.load_task_state_node import LoadTaskStateNode
from workflows.sdlc_flow_workflow_nodes.patch_docs_node import PatchDocsNode
from workflows.sdlc_flow_workflow_nodes.pull_request_node import PullRequestNode
from workflows.sdlc_flow_workflow_nodes.review_router_node import ReviewRouterNode
from workflows.sdlc_flow_workflow_nodes.save_state_node import SaveStateNode
from workflows.sdlc_flow_workflow_nodes.setup_worktree_node import SetupWorktreeNode
from workflows.sdlc_flow_workflow_nodes.spec_exists_router_node import (
    SpecExistsRouterNode,
)
from workflows.sdlc_flow_workflow_nodes.task_queue_router_node import (
    TaskQueueRouterNode,
)
from workflows.sdlc_flow_workflow_nodes.test_task_node import TestTaskNode
from workflows.sdlc_flow_workflow_nodes.triage_task_node import (
    TriageRouterNode,
    TriageTaskNode,
)
from workflows.sdlc_flow_workflow_nodes.update_task_status_node import (
    UpdateTaskStatusNode,
)
from workflows.sdlc_flow_workflow_nodes.wrap_up_node import WrapUpNode
from workflows.workflow_registry import WorkflowRegistry

_EXPECTED_NODES = {
    SetupWorktreeNode,
    SpecExistsRouterNode,
    GenerateTasksNode,
    LoadTaskStateNode,
    TaskQueueRouterNode,
    ImplementTaskNode,
    TestTaskNode,
    TriageTaskNode,
    TriageRouterNode,
    ConsolidatedReviewNode,
    ReviewRouterNode,
    UpdateTaskStatusNode,
    SaveStateNode,
    PatchDocsNode,
    WrapUpNode,
    PullRequestNode,
}


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------


class TestSDLCFlowWorkflowSchema:
    def test_schema_passes_validator(self):
        """WorkflowValidator accepts the declared (acyclic) DAG."""
        WorkflowValidator(SDLCFlowWorkflow.workflow_schema).validate()

    def test_schema_has_correct_start_node(self):
        assert SDLCFlowWorkflow.workflow_schema.start is SetupWorktreeNode

    def test_schema_has_all_nodes(self):
        found = {nc.node for nc in SDLCFlowWorkflow.workflow_schema.nodes}
        assert found == _EXPECTED_NODES

    def test_routers_marked_is_router(self):
        configs = {nc.node: nc for nc in SDLCFlowWorkflow.workflow_schema.nodes}
        for router_cls in (
            SpecExistsRouterNode,
            TaskQueueRouterNode,
            TriageRouterNode,
            ReviewRouterNode,
        ):
            assert configs[router_cls].is_router is True
        for non_router_cls in _EXPECTED_NODES - {
            SpecExistsRouterNode,
            TaskQueueRouterNode,
            TriageRouterNode,
            ReviewRouterNode,
        }:
            assert configs[non_router_cls].is_router is False

    def test_event_schema_wired(self):
        assert SDLCFlowWorkflow.workflow_schema.event_schema is SDLCFlowEventSchema

    def test_workflow_description_filled(self):
        assert SDLCFlowWorkflow.workflow_schema.description


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestSDLCFlowRegistration:
    def test_registered_in_workflow_registry(self):
        assert WorkflowRegistry.SDLC_FLOW.value is SDLCFlowWorkflow

    def test_registered_in_schema_map(self):
        assert WorkflowRegistry.SDLC_FLOW.name in SCHEMA_MAP
        assert SCHEMA_MAP[WorkflowRegistry.SDLC_FLOW.name] is SDLCFlowEventSchema

    def test_schema_registry_completeness(self):
        """Every WorkflowRegistry member has a SCHEMA_MAP entry (standing rule 6)."""
        for member in WorkflowRegistry:
            assert member.name in SCHEMA_MAP, f"{member.name} missing from SCHEMA_MAP"


# ---------------------------------------------------------------------------
# E2E smoke test — full DAG run, all agents + subprocess mocked
# ---------------------------------------------------------------------------


def _make_task(**overrides) -> dict:
    defaults = {
        "task_id": 1,
        "title": "Add health check endpoint",
        "description": "Add a /healthz endpoint returning 200.",
        "acceptance_criteria": ["GET /healthz returns 200"],
        "status": "pending",
        "validation_commands": [],
        "attempt_count": 0,
        "max_attempts": 3,
    }
    defaults.update(overrides)
    return defaults


def _seed_worktree(tmp_path, spec_slug: str, tasks: list[dict]) -> None:
    """Pre-create the (resume-mode) worktree dir + tasks.json on disk."""
    worktree = tmp_path / "trees" / f"sdlc/{spec_slug}"
    tasks_dir = worktree / "planning" / spec_slug
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")


def _fake_run_agent_recorded_factory(triage_verdict="PASS", review_verdict="PASS"):
    """Build a fake ``AgentNode.run_agent_recorded`` dispatching by node class."""

    def _fake_run_agent_recorded(self, task_context, user_prompt):  # noqa: ARG001
        name = type(self).__name__
        if name == "GenerateTasksNode":
            output = GenerateTasksNode.OutputType(
                tasks=[
                    GeneratedTask(
                        task_id=1,
                        title="Add health check endpoint",
                        description="Add a /healthz endpoint returning 200.",
                        acceptance_criteria=["GET /healthz returns 200"],
                    )
                ],
                tasks_markdown="### 1. Add health check endpoint\n\nAdd a /healthz endpoint.",
            )
        elif name == "ImplementTaskNode":
            output = ImplementTaskNode.OutputType(
                summary="Implemented the health check endpoint.",
                modified_files=["app/routes/healthz.py"],
                tests_added=["tests/routes/test_healthz.py"],
            )
        elif name == "TriageTaskNode":
            output = TriageTaskNode.OutputType(
                verdict=triage_verdict, reason="mocked triage verdict"
            )
        elif name == "ConsolidatedReviewNode":
            output = ConsolidatedReviewNode.OutputType(
                verdict=review_verdict, summary="mocked review", issues=[]
            )
        elif name == "PatchDocsNode":
            output = PatchDocsNode.OutputType(
                summary="Patched docs referencing healthz.",
                files_patched=["docs/api-reference.md"],
            )
        else:
            raise AssertionError(f"unexpected agent node: {name}")

        result = MagicMock()
        result.output = output
        return result

    return _fake_run_agent_recorded


def _run_workflow(
    tmp_path,
    monkeypatch,
    tasks: list[dict],
    spec_slug: str = "demo-spec",
    auto_pr: bool = True,
    triage_verdict: str = "PASS",
    review_verdict: str = "PASS",
    test_task_results: list[dict] | None = None,
    subprocess_calls: list[list[str]] | None = None,
    seed_tasks: bool = True,
) -> TaskContext:
    """Run the full workflow with every agent and subprocess boundary mocked.

    ``subprocess_calls``, if given, is appended to with every command list
    passed to the (single, shared) mocked ``subprocess.run`` — lets a caller
    assert which git/gh commands actually ran (e.g. "no push/PR call when
    auto_pr=False") without fighting over which module's patch "wins" (see
    ``_fake_subprocess_run`` docstring below).
    """
    monkeypatch.chdir(tmp_path)
    if seed_tasks:
        _seed_worktree(tmp_path, spec_slug, tasks)

    fake_run_agent_recorded = _fake_run_agent_recorded_factory(
        triage_verdict=triage_verdict, review_verdict=review_verdict
    )

    def _fake_subprocess_run(command, *_args, **_kwargs):
        """Dispatch on the git/gh subcommand — every SDLC node imports the
        same stdlib ``subprocess`` module object, so a single patch target
        (``subprocess.run``) is shared across every node's ``subprocess.run``
        call; per-module patches on that same underlying attribute would
        clobber one another instead of composing."""
        if subprocess_calls is not None:
            subprocess_calls.append(list(command))
        if command[0] == "gh":
            return MagicMock(returncode=0, stdout="https://github.com/x/y/pull/1", stderr="")
        if command[:2] == ["git", "diff"]:
            return MagicMock(returncode=0, stdout="diff --git a b", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    patches = [
        # Every sdlc_flow AgentNode subclass writes ``self.agent._system_prompts``
        # directly in process() (to thread real per-task values into the
        # already-built Agent) before ever calling run_agent_recorded, so
        # ``self.agent`` must exist even though run_agent_recorded is faked.
        patch.object(AgentNode, "__init__", lambda self: setattr(self, "agent", MagicMock())),
        patch.object(AgentNode, "run_agent_recorded", fake_run_agent_recorded),
        patch("subprocess.run", side_effect=_fake_subprocess_run),
    ]

    if test_task_results is not None:
        calls = {"n": 0}

        def _fake_test_process(self, task_context):
            idx = min(calls["n"], len(test_task_results) - 1)
            calls["n"] += 1
            task_context.update_node(
                node_name="TestTaskNode", result=test_task_results[idx]
            )
            return task_context

        patches.append(patch.object(TestTaskNode, "process", _fake_test_process))

    ctxs: list[TaskContext] = []
    _apply_patches(patches, lambda: ctxs.append(
        SDLCFlowWorkflow().run(
            {"spec_slug": spec_slug, "resume": True, "auto_pr": auto_pr}
        )
    ))
    return ctxs[0]


def _apply_patches(patches, fn):
    """Enter every patch in ``patches``, call ``fn()``, then unwind cleanly."""
    if not patches:
        fn()
        return
    with patches[0]:
        _apply_patches(patches[1:], fn)


_PASSING_TEST_RESULT = {"all_passed": True, "check_results": [], "failure_summary": ""}
_FAILING_TEST_RESULT = {
    "all_passed": False,
    "check_results": [],
    "failure_summary": "pytest: 1 failed",
}


class TestSDLCFlowWorkflowRunHappyPath:
    def test_happy_path_single_task(self, tmp_path, monkeypatch):
        """One task, passes on the first attempt: full DAG traversal to a PR."""
        ctx = _run_workflow(tmp_path, monkeypatch, [_make_task()])

        expected_order = [
            "SetupWorktreeNode",
            "SpecExistsRouterNode",
            "LoadTaskStateNode",
            "TaskQueueRouterNode",
            "ImplementTaskNode",
            "TestTaskNode",
            "TriageTaskNode",
            "TriageRouterNode",
            "ConsolidatedReviewNode",
            "ReviewRouterNode",
            "UpdateTaskStatusNode",
            "SaveStateNode",
            "PatchDocsNode",
            "WrapUpNode",
            "PullRequestNode",
        ]
        for node_name in expected_order:
            assert node_name in ctx.nodes, f"{node_name} did not run"
            assert ctx.node_runs[node_name].status == NodeStatus.SUCCESS

        # TaskQueueRouterNode ran twice (dispatch task 1, then end-of-loop);
        # only the final (no-pending-tasks) routing decision survives under
        # its own node name since TaskContext.nodes is keyed by node name.
        assert ctx.nodes["TaskQueueRouterNode"]["next_node"] == "PatchDocsNode"

        final_state = ctx.get_node_output("UpdateTaskStatusNode")["result"]
        assert final_state["tasks"][0]["status"] == "done"
        assert final_state["telemetry"]["tasks_passed"] == 1

        pr_output = ctx.get_node_output("PullRequestNode")["result"]
        assert pr_output["skipped"] is False
        assert pr_output["pr_url"] == "https://github.com/x/y/pull/1"


class TestSDLCFlowWorkflowRunRetryLoop:
    def test_retry_loop(self, tmp_path, monkeypatch):
        """Fails once (RETRYABLE), then passes: ImplementTaskNode runs twice."""
        implement_calls = {"n": 0}
        real_process = ImplementTaskNode.process

        def _counting_process(self, task_context):
            implement_calls["n"] += 1
            return real_process(self, task_context)

        with patch.object(ImplementTaskNode, "process", _counting_process):
            ctx = _run_workflow(
                tmp_path,
                monkeypatch,
                [_make_task()],
                triage_verdict="RETRYABLE",
                test_task_results=[_FAILING_TEST_RESULT, _PASSING_TEST_RESULT],
            )

        assert implement_calls["n"] == 2
        # The run still reaches the terminal PR node after the retry succeeds.
        assert "PullRequestNode" in ctx.nodes


class TestSDLCFlowWorkflowRunBailPath:
    def test_bail_path(self, tmp_path, monkeypatch):
        """max_attempts already exhausted: MAJOR_BAIL forced without an agent
        call, routing straight to WrapUpNode -> PullRequestNode, skipping
        ConsolidatedReviewNode / UpdateTaskStatusNode entirely."""
        ctx = _run_workflow(
            tmp_path,
            monkeypatch,
            [_make_task(max_attempts=1, attempt_count=1)],
            test_task_results=[_FAILING_TEST_RESULT],
        )

        triage_result = ctx.get_node_output("TriageTaskNode")["result"]
        assert triage_result["verdict"] == "MAJOR_BAIL"

        assert "ConsolidatedReviewNode" not in ctx.nodes
        assert "UpdateTaskStatusNode" not in ctx.nodes
        assert "WrapUpNode" in ctx.nodes
        assert "PullRequestNode" in ctx.nodes


class TestSDLCFlowWorkflowRunAutoPrFalse:
    def test_auto_pr_false_skips_pr_creation(self, tmp_path, monkeypatch):
        """auto_pr=False: PullRequestNode records a skip, no git push / gh call."""
        calls: list[list[str]] = []
        ctx = _run_workflow(
            tmp_path,
            monkeypatch,
            [_make_task()],
            auto_pr=False,
            subprocess_calls=calls,
        )

        assert not any(cmd[:2] == ["git", "push"] for cmd in calls)
        assert not any(cmd[0] == "gh" for cmd in calls)

        pr_output = ctx.get_node_output("PullRequestNode")["result"]
        assert pr_output == {"pr_url": None, "skipped": True}


class TestSDLCFlowWorkflowGeneratesSpec:
    def test_generates_spec_when_missing_then_runs_it(self, tmp_path, monkeypatch):
        """No tasks.json on disk: SpecExistsRouterNode -> GenerateTasksNode
        (which writes tasks.json + tasks.md) -> LoadTaskStateNode picks up the
        generated spec, and the run completes end-to-end to a PR."""
        ctx = _run_workflow(tmp_path, monkeypatch, [_make_task()], seed_tasks=False)

        # The planning fallback fired.
        assert ctx.nodes["SpecExistsRouterNode"]["next_node"] == "GenerateTasksNode"
        assert "GenerateTasksNode" in ctx.nodes
        gen = ctx.get_node_output("GenerateTasksNode")["result"]
        assert gen["task_count"] == 1

        # GenerateTasksNode wrote a real tasks.json into the worktree spec dir,
        # which LoadTaskStateNode then bootstrapped into SDLCState.
        tasks_json = (
            tmp_path / "trees" / "sdlc/demo-spec" / "planning" / "demo-spec" / "tasks.json"
        )
        assert tasks_json.exists()

        # The generated task ran the full loop through to a PR.
        for node_name in ("LoadTaskStateNode", "ImplementTaskNode", "PullRequestNode"):
            assert node_name in ctx.nodes
            assert ctx.node_runs[node_name].status == NodeStatus.SUCCESS

        final_state = ctx.get_node_output("UpdateTaskStatusNode")["result"]
        assert final_state["tasks"][0]["status"] == "done"
