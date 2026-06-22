"""Provider-routing tests for the Claude Code providers.

Verifies that an ``AgentNode`` configured with ``CLAUDE_CODE_SDK`` or
``CLAUDE_CODE_SESSION`` builds a ``ClaudeCodeModel`` (over the matching backend
``ClaudeAgentSdkBackend`` / ``BastionSessionBackend``) through the
``__get_model_instance`` factory, and that ``run_agent_recorded`` stamps
``{input_tokens, output_tokens, model}`` usage and stores serializable output
without touching the network, the ``claude`` CLI, or the ``bastion`` binary.
"""

import asyncio

from pydantic import BaseModel
from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart
from pydantic_ai.models import ModelRequestParameters

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import NodeRun, NodeStatus, TaskContext
from services.claude_code import (
    BastionSessionBackend,
    ClaudeAgentSdkBackend,
    ClaudeCodeModel,
    ClaudeResult,
)


class _Output(BaseModel):
    """Structured output type standing in for a node's ``OutputType``."""

    label: str


class StubClaudeSdkNode(AgentNode):
    """An AgentNode wired to the CLAUDE_CODE_SDK provider for routing tests."""

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt="be helpful",
            output_type=_Output,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="opus",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context


def test_provider_enum_value():
    assert ModelProvider.CLAUDE_CODE_SDK.value == "claude_code_sdk"


def test_node_builds_claude_code_model_over_sdk_backend():
    node = StubClaudeSdkNode()

    assert isinstance(node.agent.model, ClaudeCodeModel)
    assert node.agent.model.model_name == "opus"
    assert isinstance(node.agent.model._backend, ClaudeAgentSdkBackend)


def test_run_agent_recorded_stamps_real_usage_via_fake_backend():
    """Drive the full node path with a faked backend (no CLI/network)."""

    class FakeBackend:
        async def run(self, prompt, *, system, model, schema) -> ClaudeResult:
            return ClaudeResult(
                model=model,
                structured={"label": "hi there"},
                input_tokens=13,
                output_tokens=4,
            )

    node = StubClaudeSdkNode()
    # Swap the SDK backend for a fake one so no `claude` CLI is spawned.
    node.agent.model._backend = FakeBackend()

    ctx = TaskContext(event={"input": "x"})
    ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)

    node.run_agent_recorded(ctx, "say hi")

    usage = ctx.node_runs[node.node_name].usage
    assert usage == {"input_tokens": 13, "output_tokens": 4, "model": "opus"}
    # Output is the validated OutputType, stored JSON-serializable; the whole
    # context still dumps to JSON (data-contract guarantee).
    assert ctx.nodes[node.node_name]["output"] == {"label": "hi there"}
    ctx.model_dump(mode="json")


class StubClaudeSessionNode(AgentNode):
    """An AgentNode wired to the CLAUDE_CODE_SESSION provider for routing."""

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt="be helpful",
            output_type=_Output,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SESSION,
            model_name="opus",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context


def test_session_provider_enum_value():
    assert ModelProvider.CLAUDE_CODE_SESSION.value == "claude_code_session"


def test_node_builds_claude_code_model_over_bastion_backend():
    node = StubClaudeSessionNode()

    assert isinstance(node.agent.model, ClaudeCodeModel)
    assert node.agent.model.model_name == "opus"
    assert isinstance(node.agent.model._backend, BastionSessionBackend)


def test_session_run_agent_recorded_stamps_model_with_none_tokens():
    """Session mode cannot report tokens; model is still recorded."""

    class FakeBastionBackend:
        async def run(self, prompt, *, system, model, schema) -> ClaudeResult:
            # Mirror BastionSessionBackend: no token/cost telemetry available.
            return ClaudeResult(
                model=model,
                structured={"label": "from session"},
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
                session_id=None,
            )

    node = StubClaudeSessionNode()
    # Swap the bastion backend for a fake one so no `bastion` binary is spawned.
    node.agent.model._backend = FakeBastionBackend()

    ctx = TaskContext(event={"input": "x"})
    ctx.node_runs[node.node_name] = NodeRun(status=NodeStatus.RUNNING)

    node.run_agent_recorded(ctx, "say hi")

    usage = ctx.node_runs[node.node_name].usage
    assert usage == {
        "input_tokens": None,
        "output_tokens": None,
        "model": "opus",
    }
    assert ctx.nodes[node.node_name]["output"] == {"label": "from session"}
    ctx.model_dump(mode="json")


def test_claude_code_model_request_path_through_backend():
    """The model built by the factory drives the backend and returns a tuple."""

    class FakeBackend:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def run(self, prompt, *, system, model, schema) -> ClaudeResult:
            self.calls.append(
                {"prompt": prompt, "system": system, "model": model, "schema": schema}
            )
            return ClaudeResult(model=model, text="ok", input_tokens=2, output_tokens=1)

    backend = FakeBackend()
    model = ClaudeCodeModel(backend=backend, model_name="opus")
    messages = [ModelRequest(parts=[UserPromptPart(content="hello")])]
    params = ModelRequestParameters(
        function_tools=[], allow_text_output=True, output_tools=[]
    )

    out = asyncio.run(model.request(messages, None, params))

    assert isinstance(out, tuple) and len(out) == 2
    response, usage = out
    assert isinstance(response, ModelResponse)
    assert usage.request_tokens == 2
    assert backend.calls[0]["prompt"] == "hello"
    assert backend.calls[0]["model"] == "opus"
