"""Unit tests for per-node token/cost capture on AgentNode and ToolUseNode."""

from unittest.mock import MagicMock, patch

import pytest

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.nodes.base import Node
from core.nodes.tool_use import ToolUseNode
from core.task import NodeRun, NodeStatus, TaskContext


# ---------------------------------------------------------------------------
# ToolUseNode usage capture
# ---------------------------------------------------------------------------


class ConcreteToolUseNode(ToolUseNode):
    """Minimal concrete subclass for testing usage capture."""

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


def _end_turn_response(input_tokens: int, output_tokens: int):
    r = MagicMock()
    r.stop_reason = "end_turn"
    r.content = []
    r.usage = MagicMock(input_tokens=input_tokens, output_tokens=output_tokens)
    return r


class TestToolUseNodeUsage:
    @pytest.fixture
    def node(self, monkeypatch):
        monkeypatch.setenv("TOOL_USE_MODEL", "claude-haiku-4-5-20251001")
        with patch("core.nodes.tool_use.anthropic.Anthropic") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            node = ConcreteToolUseNode()
            node._client = mock_instance
            yield node, mock_instance

    def test_usage_recorded_onto_node_run(self, node):
        node_obj, client = node
        client.messages.create.return_value = _end_turn_response(11, 7)
        ctx = TaskContext(event={"input": "x"})
        ctx.node_runs[node_obj.node_name] = NodeRun(status=NodeStatus.RUNNING)

        node_obj.process(ctx)

        usage = ctx.node_runs[node_obj.node_name].usage
        assert usage is not None
        assert usage["input_tokens"] == 11
        assert usage["output_tokens"] == 7
        assert usage["model"] == "claude-haiku-4-5-20251001"

    def test_usage_accumulates_across_iterations(self, node):
        node_obj, client = node
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "id1"
        tool_block.name = "echo"
        tool_block.input = {"text": "hi"}
        first = MagicMock()
        first.stop_reason = "tool_use"
        first.content = [tool_block]
        first.usage = MagicMock(input_tokens=4, output_tokens=3)
        client.messages.create.side_effect = [first, _end_turn_response(10, 5)]
        ctx = TaskContext(event={"input": "x"})
        ctx.node_runs[node_obj.node_name] = NodeRun(status=NodeStatus.RUNNING)

        node_obj.process(ctx)

        usage = ctx.node_runs[node_obj.node_name].usage
        assert usage["input_tokens"] == 14
        assert usage["output_tokens"] == 8

    def test_no_node_run_seeded_does_not_raise(self, node):
        node_obj, client = node
        client.messages.create.return_value = _end_turn_response(1, 1)
        ctx = TaskContext(event={"input": "x"})

        # No NodeRun seeded for this node — must not raise, records nothing.
        result = node_obj.process(ctx)
        assert result is ctx
        assert node_obj.node_name not in ctx.node_runs


# ---------------------------------------------------------------------------
# AgentNode usage capture
# ---------------------------------------------------------------------------


class StubAgentNode(AgentNode):
    """Minimal concrete AgentNode for testing run_agent_recorded."""

    def __init__(self):
        # Skip the real Agent/model construction; the test patches self.agent.
        pass

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt="be helpful",
            output_type=None,
            deps_type=None,
            model_provider=ModelProvider.OPENAI,
            model_name="gpt-4.1",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context


class TestAgentNodeUsage:
    def test_run_agent_recorded_stamps_usage(self):
        node = StubAgentNode()
        result = MagicMock()
        result.usage.return_value = MagicMock(input_tokens=5, output_tokens=9)
        node.agent = MagicMock()
        node.agent.run_sync.return_value = result

        ctx = TaskContext(event={"input": "x"})
        ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)

        node.run_agent_recorded(ctx, "hi")

        assert ctx.node_runs[node.node_name].usage == {
            "input_tokens": 5,
            "output_tokens": 9,
            "model": "gpt-4.1",
        }

    def test_run_agent_recorded_old_token_names(self):
        """pydantic-ai >=0.1.5 exposes request_tokens/response_tokens."""
        node = StubAgentNode()
        result = MagicMock()
        # Emulate the older Usage shape: no input_tokens/output_tokens attrs.
        usage = MagicMock(spec=["request_tokens", "response_tokens"])
        usage.request_tokens = 12
        usage.response_tokens = 3
        result.usage.return_value = usage
        node.agent = MagicMock()
        node.agent.run_sync.return_value = result

        ctx = TaskContext(event={"input": "x"})
        ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)

        node.run_agent_recorded(ctx, "hi")

        assert ctx.node_runs[node.node_name].usage["input_tokens"] == 12
        assert ctx.node_runs[node.node_name].usage["output_tokens"] == 3

    def test_run_agent_recorded_returns_result(self):
        node = StubAgentNode()
        result = MagicMock()
        result.usage.return_value = MagicMock(input_tokens=1, output_tokens=1)
        node.agent = MagicMock()
        node.agent.run_sync.return_value = result

        ctx = TaskContext(event={"input": "x"})
        ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)

        assert node.run_agent_recorded(ctx, "hi") is result


# ---------------------------------------------------------------------------
# Non-LLM node records no usage
# ---------------------------------------------------------------------------


class PlainNode(Node):
    """A non-LLM node that records output but no token usage."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node(self.node_name, ran=True)
        return task_context


def test_non_llm_node_has_no_usage():
    node = PlainNode()
    ctx = TaskContext(event={"input": "x"})
    ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)

    node.process(ctx)

    assert ctx.node_runs[node.node_name].usage is None
