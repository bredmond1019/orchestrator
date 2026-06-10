"""Unit tests for ToolUseNode in app/core/nodes/tool_use.py."""

from unittest.mock import MagicMock, patch

import pytest

from core.nodes.tool_use import ToolUseNode
from core.task import TaskContext


class ConcreteToolUseNode(ToolUseNode):
    """Minimal concrete subclass for testing the abstract loop."""

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "name": "echo",
                "description": "Echoes input",
                "input_schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                },
            }
        ]

    def handle_tool_call(
        self, tool_name: str, tool_input: dict, task_context: TaskContext
    ) -> str:
        return f"echo:{tool_input.get('text', '')}"


@pytest.fixture
def mock_anthropic_client():
    with patch("core.nodes.tool_use.anthropic.Anthropic") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def node(mock_anthropic_client, monkeypatch):
    monkeypatch.setenv("TOOL_USE_MODEL", "claude-haiku-4-5-20251001")
    return ConcreteToolUseNode()


@pytest.fixture
def ctx():
    return TaskContext(event={"input": "test"})


def _end_turn_response():
    r = MagicMock()
    r.stop_reason = "end_turn"
    r.content = []
    return r


def _tool_use_response(tool_id: str, name: str, tool_input: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = tool_input
    r = MagicMock()
    r.stop_reason = "tool_use"
    r.content = [block]
    return r


class TestLoopTerminatesOnEndTurn:
    def test_single_end_turn_makes_exactly_one_api_call(
        self, node, mock_anthropic_client, ctx
    ):
        mock_anthropic_client.messages.create.return_value = _end_turn_response()
        result = node.process(ctx)
        assert mock_anthropic_client.messages.create.call_count == 1
        assert result is ctx


class TestToolCallDispatch:
    def test_handle_tool_call_invoked_then_loop_continues(
        self, node, mock_anthropic_client, ctx
    ):
        mock_anthropic_client.messages.create.side_effect = [
            _tool_use_response("id1", "echo", {"text": "hello"}),
            _end_turn_response(),
        ]
        node.process(ctx)
        assert mock_anthropic_client.messages.create.call_count == 2

    def test_tool_result_appended_to_messages_on_second_call(
        self, node, mock_anthropic_client, ctx
    ):
        mock_anthropic_client.messages.create.side_effect = [
            _tool_use_response("id1", "echo", {"text": "world"}),
            _end_turn_response(),
        ]
        node.process(ctx)
        second_call = mock_anthropic_client.messages.create.call_args_list[1]
        messages = second_call.kwargs.get("messages") or second_call[1]["messages"]
        user_msgs = [m for m in messages if m["role"] == "user"]
        last_user_content = user_msgs[-1]["content"]
        assert any(
            isinstance(r, dict) and r.get("type") == "tool_result"
            for r in last_user_content
        )


class TestMaxIterationsGuard:
    def test_loop_exits_at_max_iterations(self, node, mock_anthropic_client, ctx):
        node.max_iterations = 3
        mock_anthropic_client.messages.create.return_value = _tool_use_response(
            "id1", "echo", {"text": "x"}
        )
        node.process(ctx)
        assert mock_anthropic_client.messages.create.call_count == 3

    def test_does_not_raise_on_max_iterations(self, node, mock_anthropic_client, ctx):
        node.max_iterations = 2
        mock_anthropic_client.messages.create.return_value = _tool_use_response(
            "id1", "echo", {"text": "x"}
        )
        result = node.process(ctx)
        assert result is ctx
