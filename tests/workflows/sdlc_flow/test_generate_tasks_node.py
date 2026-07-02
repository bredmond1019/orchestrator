"""Unit tests for GenerateTasksNode + SpecExistsRouterNode.

Covers:
- SpecExistsRouterNode: routes to LoadTaskStateNode when a spec (tasks.json or
  sdlc-flow-state.json) already exists, else to GenerateTasksNode.
- GenerateTasksNode: gathers source .md context, invokes the (mocked) Opus
  agent, and writes both tasks.md and tasks.json into the worktree spec dir.

Agents are mocked — no real pydantic-ai Agent is constructed for the
GenerateTasksNode process test, so it needs no API key or network.
"""

import json
from unittest.mock import MagicMock

from core.task import NodeRun, NodeStatus, TaskContext
from schemas.sdlc_schema import SDLCFlowEventSchema
from workflows.sdlc_flow_workflow_nodes.generate_tasks_node import (
    GeneratedTask,
    GenerateTasksNode,
)
from workflows.sdlc_flow_workflow_nodes.load_task_state_node import LoadTaskStateNode
from workflows.sdlc_flow_workflow_nodes.spec_exists_router_node import (
    SpecExistsRouterNode,
    _SpecExistsRouter,
)


def _make_agent_node(node_cls):
    node = node_cls.__new__(node_cls)
    node.agent = MagicMock()
    return node


def _result_for(output) -> MagicMock:
    result = MagicMock()
    result.output = output
    result.usage.return_value = MagicMock(input_tokens=10, output_tokens=20)
    return result


def _make_ctx(worktree_path: str, spec_slug: str = "demo-spec") -> TaskContext:
    ctx = TaskContext(event=SDLCFlowEventSchema(spec_slug=spec_slug))
    ctx.nodes["SetupWorktreeNode"] = {
        "result": {"worktree_path": worktree_path, "branch_name": f"sdlc/{spec_slug}"}
    }
    return ctx


# ---------------------------------------------------------------------------
# SpecExistsRouterNode
# ---------------------------------------------------------------------------


class TestSpecExistsRouterNode:
    def test_routes_to_load_when_tasks_json_present(self, tmp_path):
        spec_dir = tmp_path / "planning" / "demo-spec"
        spec_dir.mkdir(parents=True)
        (spec_dir / "tasks.json").write_text("[]", encoding="utf-8")

        ctx = _make_ctx(str(tmp_path))
        next_node = _SpecExistsRouter().determine_next_node(ctx)
        assert isinstance(next_node, LoadTaskStateNode)

    def test_routes_to_load_when_state_json_present(self, tmp_path):
        spec_dir = tmp_path / "planning" / "demo-spec"
        spec_dir.mkdir(parents=True)
        (spec_dir / "sdlc-flow-state.json").write_text("{}", encoding="utf-8")

        ctx = _make_ctx(str(tmp_path))
        next_node = _SpecExistsRouter().determine_next_node(ctx)
        assert isinstance(next_node, LoadTaskStateNode)

    def test_routes_to_generate_when_spec_missing(self, tmp_path):
        ctx = _make_ctx(str(tmp_path))
        next_node = _SpecExistsRouter().determine_next_node(ctx)
        assert isinstance(next_node, GenerateTasksNode)

    def test_router_process_records_next_node(self, tmp_path):
        ctx = _make_ctx(str(tmp_path))
        router = SpecExistsRouterNode()
        router.process(ctx)

        assert ctx.nodes["SpecExistsRouterNode"]["next_node"] == "GenerateTasksNode"

    def test_router_has_no_fallback(self):
        assert SpecExistsRouterNode().fallback is None


# ---------------------------------------------------------------------------
# GenerateTasksNode
# ---------------------------------------------------------------------------


class TestGenerateTasksNode:
    def test_writes_tasks_md_and_json(self, tmp_path):
        spec_dir = tmp_path / "planning" / "demo-spec"
        spec_dir.mkdir(parents=True)
        (spec_dir / "plan.md").write_text("# Plan\nBuild a thing.", encoding="utf-8")

        node = _make_agent_node(GenerateTasksNode)
        output = GenerateTasksNode.OutputType(
            tasks=[
                GeneratedTask(
                    task_id=1,
                    title="Add the thing",
                    description="Implement the thing.",
                    acceptance_criteria=["The thing exists"],
                )
            ],
            tasks_markdown="### 1. Add the thing\n\nImplement the thing.",
        )
        node.agent.run_sync.return_value = _result_for(output)

        ctx = _make_ctx(str(tmp_path))
        ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)

        node.process(ctx)

        tasks_json = json.loads((spec_dir / "tasks.json").read_text(encoding="utf-8"))
        assert tasks_json == [
            {
                "task_id": 1,
                "title": "Add the thing",
                "description": "Implement the thing.",
                "acceptance_criteria": ["The thing exists"],
            }
        ]
        assert (spec_dir / "tasks.md").read_text(encoding="utf-8").startswith("### 1.")

        stored = ctx.nodes["GenerateTasksNode"]["result"]
        assert stored["task_count"] == 1
        assert stored["tasks_json"].endswith("tasks.json")

    def test_gathers_context_excludes_task_files(self, tmp_path):
        spec_dir = tmp_path / "planning" / "demo-spec"
        spec_dir.mkdir(parents=True)
        (spec_dir / "notes.md").write_text("Source notes.", encoding="utf-8")
        (spec_dir / "tasks.md").write_text("Should be ignored.", encoding="utf-8")

        context = GenerateTasksNode._gather_context(spec_dir)
        assert "Source notes." in context
        assert "Should be ignored." not in context
