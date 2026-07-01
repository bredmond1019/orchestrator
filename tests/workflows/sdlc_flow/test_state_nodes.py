"""Unit tests for LoadTaskStateNode and SaveStateNode."""

import json
from unittest.mock import MagicMock, patch

import pytest
from core.task import TaskContext
from schemas.sdlc_schema import SDLCFlowEventSchema, SDLCState, SDLCTask, SDLCTaskStatus
from workflows.sdlc_flow_workflow_nodes.load_task_state_node import LoadTaskStateNode
from workflows.sdlc_flow_workflow_nodes.save_state_node import SaveStateNode


def _make_state(n_tasks: int = 3) -> SDLCState:
    tasks = [
        SDLCTask(task_id=i, title=f"Task {i}", description=f"Desc {i}")
        for i in range(1, n_tasks + 1)
    ]
    return SDLCState(spec_slug="test-spec", tasks=tasks)


def _make_ctx(worktree_path: str, **event_overrides) -> TaskContext:
    defaults = {"spec_slug": "test-spec"}
    defaults.update(event_overrides)
    ctx = TaskContext(event=SDLCFlowEventSchema(**defaults))
    ctx.nodes["SetupWorktreeNode"] = {
        "result": {"worktree_path": worktree_path, "branch_name": "sdlc/test-spec"}
    }
    return ctx


class TestLoadTaskStateNode:
    def test_loads_existing_state_file(self, tmp_path):
        state = _make_state()
        state_dir = tmp_path / "planning" / "test-spec"
        state_dir.mkdir(parents=True)
        state_path = state_dir / "sdlc-flow-state.json"
        state_path.write_text(state.model_dump_json(), encoding="utf-8")

        ctx = _make_ctx(str(tmp_path))
        node = LoadTaskStateNode()
        result = node.process(ctx)

        assert result is ctx
        output = ctx.get_node_output("LoadTaskStateNode")["result"]
        assert output["spec_slug"] == "test-spec"
        assert len(output["tasks"]) == 3

    def test_task_range_filtering(self, tmp_path):
        state = _make_state()
        state_dir = tmp_path / "planning" / "test-spec"
        state_dir.mkdir(parents=True)
        state_path = state_dir / "sdlc-flow-state.json"
        state_path.write_text(state.model_dump_json(), encoding="utf-8")

        ctx = _make_ctx(str(tmp_path), task_range="1,3")
        node = LoadTaskStateNode()
        node.process(ctx)

        output = ctx.get_node_output("LoadTaskStateNode")["result"]
        task_ids = [task["task_id"] for task in output["tasks"]]
        assert task_ids == [1, 3]

    def test_missing_file_raises(self, tmp_path):
        ctx = _make_ctx(str(tmp_path))
        node = LoadTaskStateNode()
        with pytest.raises(FileNotFoundError, match="test-spec"):
            node.process(ctx)

    def test_initial_state_from_tasks_json(self, tmp_path):
        state_dir = tmp_path / "planning" / "test-spec"
        state_dir.mkdir(parents=True)
        tasks_path = state_dir / "tasks.json"
        tasks_data = [
            {"task_id": 1, "title": "Task 1", "description": "Desc 1"},
            {"task_id": 2, "title": "Task 2", "description": "Desc 2"},
        ]
        tasks_path.write_text(json.dumps(tasks_data), encoding="utf-8")

        ctx = _make_ctx(str(tmp_path))
        node = LoadTaskStateNode()
        node.process(ctx)

        output = ctx.get_node_output("LoadTaskStateNode")["result"]
        assert output["spec_slug"] == "test-spec"
        assert len(output["tasks"]) == 2


class TestSaveStateNode:
    def test_round_trip_save(self, tmp_path):
        state = _make_state()
        ctx = _make_ctx(str(tmp_path))
        ctx.nodes["LoadTaskStateNode"] = {"result": state.model_dump()}

        with patch(
            "workflows.sdlc_flow_workflow_nodes.save_state_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            node = SaveStateNode()
            result = node.process(ctx)

        assert result is ctx
        state_path = tmp_path / "planning" / "test-spec" / "sdlc-flow-state.json"
        assert state_path.exists()
        saved = SDLCState.model_validate_json(state_path.read_text(encoding="utf-8"))
        assert saved.spec_slug == "test-spec"
        assert len(saved.tasks) == 3

        output = ctx.get_node_output("SaveStateNode")["result"]
        assert output["saved_to"] == str(state_path)

    def test_prefers_update_task_status_node_output(self, tmp_path):
        loaded_state = _make_state(n_tasks=2)
        updated_state = _make_state(n_tasks=2)
        updated_state.tasks[0].status = SDLCTaskStatus.DONE

        ctx = _make_ctx(str(tmp_path))
        ctx.nodes["LoadTaskStateNode"] = {"result": loaded_state.model_dump()}
        ctx.nodes["UpdateTaskStatusNode"] = {"result": updated_state.model_dump()}

        with patch(
            "workflows.sdlc_flow_workflow_nodes.save_state_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            node = SaveStateNode()
            node.process(ctx)

        state_path = tmp_path / "planning" / "test-spec" / "sdlc-flow-state.json"
        saved = SDLCState.model_validate_json(state_path.read_text(encoding="utf-8"))
        assert saved.tasks[0].status == "done"

    def test_git_commit_called(self, tmp_path):
        state = _make_state()
        ctx = _make_ctx(str(tmp_path))
        ctx.nodes["LoadTaskStateNode"] = {"result": state.model_dump()}

        with patch(
            "workflows.sdlc_flow_workflow_nodes.save_state_node.subprocess.run"
        ) as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            node = SaveStateNode()
            node.process(ctx)

        assert mock_run.call_count == 2
        add_args = mock_run.call_args_list[0][0][0]
        commit_args = mock_run.call_args_list[1][0][0]
        assert add_args[:2] == ["git", "add"]
        assert commit_args[:2] == ["git", "commit"]
