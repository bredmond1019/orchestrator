"""Unit tests for ImplementTaskNode.

All agents are mocked — no real Claude Code invocation, no model, no key
required. Tests verify:
- The agent is invoked exactly once with a prompt derived from the task
- The prompt threads task_title / acceptance_criteria / worktree_path
- TaskContext output is stored under the ``result`` key with the expected
  structure (per standing rule 9 — mirrors ``AgentNode``'s storage contract)
- ``process()`` returns the same TaskContext instance it received
"""

import json
from unittest.mock import MagicMock

from core.task import NodeRun, NodeStatus, TaskContext
from schemas.sdlc_schema import SDLCFlowEventSchema
from workflows.sdlc_flow_workflow_nodes.implement_task_node import ImplementTaskNode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node() -> ImplementTaskNode:
    """Construct ImplementTaskNode without building a real pydantic-ai Agent."""
    node = ImplementTaskNode.__new__(ImplementTaskNode)
    node.agent = MagicMock()
    return node


def _result_for(output) -> MagicMock:
    r = MagicMock()
    r.output = output
    r.usage.return_value = MagicMock(input_tokens=100, output_tokens=50)
    return r


def _make_ctx() -> TaskContext:
    """Seed a TaskContext per standing rule 9 (result-envelope contract)."""
    ctx = TaskContext(event=SDLCFlowEventSchema(spec_slug="test-spec"))
    ctx.nodes["SetupWorktreeNode"] = {
        "result": {"worktree_path": "/tmp/wt", "branch_name": "sdlc/test"}
    }
    ctx.nodes["TaskQueueRouterNode"] = {
        "result": {
            "current_task_id": 1,
            "title": "Implement JWT",
            "description": "Add JWT middleware",
            "acceptance_criteria": ["Validates tokens"],
        }
    }
    ctx.node_runs["ImplementTaskNode"] = NodeRun(status=NodeStatus.RUNNING)
    return ctx


def _make_output(
    summary: str = "Implemented JWT middleware.",
    modified_files: list[str] | None = None,
    tests_added: list[str] | None = None,
) -> "ImplementTaskNode.OutputType":
    return ImplementTaskNode.OutputType(
        summary=summary,
        modified_files=modified_files or ["app/middleware/jwt.py"],
        tests_added=tests_added or ["tests/middleware/test_jwt.py"],
    )


# ---------------------------------------------------------------------------
# Core behaviour
# ---------------------------------------------------------------------------


class TestImplementTaskNode:
    def test_process_calls_agent(self):
        """process() invokes the agent exactly once."""
        node = _make_node()
        node.agent.run_sync.return_value = _result_for(_make_output())

        ctx = _make_ctx()
        node.process(ctx)

        node.agent.run_sync.assert_called_once()

    def test_prompt_contains_task_fields(self):
        """The user prompt sent to the agent carries the task's title,
        description, acceptance criteria, and worktree path."""
        node = _make_node()
        node.agent.run_sync.return_value = _result_for(_make_output())

        ctx = _make_ctx()
        node.process(ctx)

        prompt = node.agent.run_sync.call_args.kwargs["user_prompt"]
        data = json.loads(prompt)
        assert data["task_title"] == "Implement JWT"
        assert data["task_description"] == "Add JWT middleware"
        assert data["acceptance_criteria"] == ["Validates tokens"]
        assert data["worktree_path"] == "/tmp/wt"

    def test_output_stored_with_result_key(self):
        """ImplementTaskNode's output is stored under the 'result' key with
        summary / modified_files / tests_added."""
        node = _make_node()
        raw = _make_output(
            summary="Added JWT middleware and tests.",
            modified_files=["app/middleware/jwt.py"],
            tests_added=["tests/middleware/test_jwt.py"],
        )
        node.agent.run_sync.return_value = _result_for(raw)

        ctx = _make_ctx()
        node.process(ctx)

        stored = ctx.get_node_output("ImplementTaskNode")["result"]
        assert stored["summary"] == "Added JWT middleware and tests."
        assert stored["modified_files"] == ["app/middleware/jwt.py"]
        assert stored["tests_added"] == ["tests/middleware/test_jwt.py"]

    def test_returns_task_context(self):
        """process() returns the same TaskContext instance it received."""
        node = _make_node()
        node.agent.run_sync.return_value = _result_for(_make_output())

        ctx = _make_ctx()
        result = node.process(ctx)

        assert result is ctx

    def test_system_prompt_rendered_with_task_fields(self):
        """The Agent's internal system prompt is re-rendered with the current
        task's fields before the agent is invoked (not the get_agent_config()
        placeholder)."""
        node = _make_node()
        node.agent.run_sync.return_value = _result_for(_make_output())

        ctx = _make_ctx()
        node.process(ctx)

        rendered = node.agent._system_prompts[0]  # pylint: disable=protected-access
        assert "Implement JWT" in rendered
        assert "Add JWT middleware" in rendered
        assert "Validates tokens" in rendered

    def test_missing_optional_breakdown_steps_defaults_to_empty(self):
        """When the current task has no breakdown_steps key, the node still
        renders the prompt (breakdown_steps defaults to an empty list)."""
        node = _make_node()
        node.agent.run_sync.return_value = _result_for(_make_output())

        ctx = _make_ctx()
        # current task dict has no "breakdown_steps" key by default
        assert "breakdown_steps" not in ctx.nodes["TaskQueueRouterNode"]["result"]

        result = node.process(ctx)

        assert result is ctx
