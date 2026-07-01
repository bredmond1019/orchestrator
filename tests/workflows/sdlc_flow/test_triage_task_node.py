"""Unit tests for TriageTaskNode + TriageRouterNode (Task 7).

Covers:
- TriageTaskNode: forces MAJOR_BAIL on max_attempts, returns PASS without a
  model call when all checks passed, and classifies via the mocked agent
  otherwise.
- TriageRouterNode / _TriageVerdictRouter: routes PASS -> ConsolidatedReviewNode,
  RETRYABLE -> ImplementTaskNode, MAJOR_BAIL -> WrapUpNode.

Agents are mocked — no real pydantic-ai Agent is constructed, so these tests
need no API key or network connection.
"""

from unittest.mock import MagicMock

from core.task import NodeRun, NodeStatus, TaskContext
from schemas.sdlc_schema import SDLCFlowEventSchema
from workflows.sdlc_flow_workflow_nodes.consolidated_review_node import (
    ConsolidatedReviewNode,
)
from workflows.sdlc_flow_workflow_nodes.implement_task_node import ImplementTaskNode
from workflows.sdlc_flow_workflow_nodes.triage_task_node import (
    TriageRouterNode,
    TriageTaskNode,
    _TriageVerdictRouter,
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


def _make_ctx(all_passed: bool, failure_summary: str = "", attempt_count: int = 0,
              max_attempts: int = 3) -> TaskContext:
    ctx = TaskContext(event=SDLCFlowEventSchema(spec_slug="test-spec"))
    ctx.nodes["TestTaskNode"] = {
        "result": {"all_passed": all_passed, "check_results": [], "failure_summary": failure_summary}
    }
    ctx.nodes["TaskQueueRouterNode"] = {
        "result": {
            "current_task_id": 1,
            "title": "Fix the bug",
            "attempt_count": attempt_count,
            "max_attempts": max_attempts,
        }
    }
    return ctx


def _seed_run(ctx: TaskContext, node) -> None:
    ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)


# ---------------------------------------------------------------------------
# TriageTaskNode
# ---------------------------------------------------------------------------


class TestTriageTaskNode:
    def test_pass_when_all_checks_passed(self):
        node = _make_agent_node(TriageTaskNode)
        ctx = _make_ctx(all_passed=True)
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes["TriageTaskNode"]["result"]
        assert stored["verdict"] == "PASS"
        # No model call needed for the passing path.
        node.agent.run_sync.assert_not_called()

    def test_forces_major_bail_when_max_attempts_reached(self):
        node = _make_agent_node(TriageTaskNode)
        ctx = _make_ctx(
            all_passed=False,
            failure_summary="Failed checks: pytest",
            attempt_count=3,
            max_attempts=3,
        )
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes["TriageTaskNode"]["result"]
        assert stored["verdict"] == "MAJOR_BAIL"
        assert "Max attempts" in stored["reason"]
        node.agent.run_sync.assert_not_called()

    def test_classifies_retryable_via_agent(self):
        node = _make_agent_node(TriageTaskNode)
        output = TriageTaskNode.OutputType(verdict="RETRYABLE", reason="Failing unit test.")
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx(
            all_passed=False,
            failure_summary="Failed checks: pytest",
            attempt_count=1,
            max_attempts=3,
        )
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes["TriageTaskNode"]["result"]
        assert stored["verdict"] == "RETRYABLE"
        assert stored["reason"] == "Failing unit test."
        node.agent.run_sync.assert_called_once()

    def test_classifies_major_bail_via_agent(self):
        node = _make_agent_node(TriageTaskNode)
        output = TriageTaskNode.OutputType(
            verdict="MAJOR_BAIL", reason="Missing dependency not in spec."
        )
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx(
            all_passed=False,
            failure_summary="ModuleNotFoundError",
            attempt_count=0,
            max_attempts=3,
        )
        _seed_run(ctx, node)

        node.process(ctx)

        stored = ctx.nodes["TriageTaskNode"]["result"]
        assert stored["verdict"] == "MAJOR_BAIL"


# ---------------------------------------------------------------------------
# TriageRouterNode / _TriageVerdictRouter
# ---------------------------------------------------------------------------


class TestTriageRouterNode:
    def _ctx_with_verdict(self, verdict: str) -> TaskContext:
        ctx = TaskContext(event=SDLCFlowEventSchema(spec_slug="test-spec"))
        ctx.nodes["TriageTaskNode"] = {"result": {"verdict": verdict, "reason": "n/a"}}
        return ctx

    def test_routes_to_review_on_pass(self):
        ctx = self._ctx_with_verdict("PASS")
        next_node = _TriageVerdictRouter().determine_next_node(ctx)
        assert isinstance(next_node, ConsolidatedReviewNode)

    def test_routes_to_implement_on_retryable(self):
        ctx = self._ctx_with_verdict("RETRYABLE")
        next_node = _TriageVerdictRouter().determine_next_node(ctx)
        assert isinstance(next_node, ImplementTaskNode)

    def test_routes_to_wrapup_on_major_bail(self):
        ctx = self._ctx_with_verdict("MAJOR_BAIL")
        next_node = _TriageVerdictRouter().determine_next_node(ctx)
        assert isinstance(next_node, WrapUpNode)

    def test_no_route_when_result_missing(self):
        ctx = TaskContext(event=SDLCFlowEventSchema(spec_slug="test-spec"))
        ctx.nodes["TriageTaskNode"] = {"result": None}
        next_node = _TriageVerdictRouter().determine_next_node(ctx)
        assert next_node is None

    def test_router_process_records_next_node(self):
        ctx = self._ctx_with_verdict("PASS")
        router = TriageRouterNode()
        router.process(ctx)

        assert "TriageRouterNode" in ctx.nodes
        assert ctx.nodes["TriageRouterNode"]["next_node"] == "ConsolidatedReviewNode"

    def test_router_has_no_fallback(self):
        router = TriageRouterNode()
        assert router.fallback is None
