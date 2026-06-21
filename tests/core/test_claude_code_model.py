"""Unit tests for ``ClaudeCodeModel`` (pydantic-ai 0.1.5 adapter).

Drives ``request`` with a fake backend for both output paths and asserts the
pinned pydantic-ai 0.1.5 contract: a 2-tuple ``(ModelResponse, Usage)`` return,
a ``TextPart`` for free text, a ``ToolCallPart`` for structured output, and
real token usage mapped onto ``Usage``.
"""

import asyncio

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import Usage

from services.claude_code import ClaudeCodeModel
from services.claude_code.backend import ClaudeResult


class FakeBackend:
    """Records the most recent ``run`` call and returns a canned ``ClaudeResult``."""

    def __init__(self, result: ClaudeResult) -> None:
        self._result = result
        self.calls: list[dict] = []

    async def run(self, prompt, *, system, model, schema) -> ClaudeResult:
        self.calls.append(
            {"prompt": prompt, "system": system, "model": model, "schema": schema}
        )
        return self._result


def _request(system: str | None, user: str) -> list:
    parts = []
    if system is not None:
        parts.append(SystemPromptPart(content=system))
    parts.append(UserPromptPart(content=user))
    return [ModelRequest(parts=parts)]


def _params(output_tools=None) -> ModelRequestParameters:
    return ModelRequestParameters(
        function_tools=[],
        allow_text_output=not output_tools,
        output_tools=output_tools or [],
    )


def test_model_properties():
    model = ClaudeCodeModel(
        backend=FakeBackend(ClaudeResult(model="x")), model_name="opus"
    )
    assert model.model_name == "opus"
    assert model.system == "claude-code"
    assert model.base_url is None


def test_customize_request_parameters_is_identity():
    model = ClaudeCodeModel(
        backend=FakeBackend(ClaudeResult(model="x")), model_name="opus"
    )
    params = _params()
    assert model.customize_request_parameters(params) is params


def test_get_instructions_returns_none():
    model = ClaudeCodeModel(
        backend=FakeBackend(ClaudeResult(model="x")), model_name="opus"
    )
    assert model._get_instructions(_request(None, "hi")) is None


def test_text_path_returns_textpart_and_usage():
    result = ClaudeResult(
        model="claude-opus-4-8",
        text="hello world",
        input_tokens=11,
        output_tokens=7,
    )
    backend = FakeBackend(result)
    model = ClaudeCodeModel(backend=backend, model_name="claude-opus-4-8")

    out = asyncio.run(model.request(_request("be terse", "say hi"), None, _params()))

    # 2-tuple return is the pinned 0.1.5 contract.
    assert isinstance(out, tuple) and len(out) == 2
    response, usage = out
    assert isinstance(response, ModelResponse)
    assert isinstance(usage, Usage)

    assert len(response.parts) == 1
    part = response.parts[0]
    assert isinstance(part, TextPart)
    assert part.content == "hello world"

    assert usage.requests == 1
    assert usage.request_tokens == 11
    assert usage.response_tokens == 7

    # Free-text path calls the backend with schema=None and the flattened prompt.
    assert backend.calls[0]["schema"] is None
    assert backend.calls[0]["system"] == "be terse"
    assert backend.calls[0]["prompt"] == "say hi"
    assert backend.calls[0]["model"] == "claude-opus-4-8"


def test_text_path_handles_missing_text():
    backend = FakeBackend(ClaudeResult(model="opus", text=None))
    model = ClaudeCodeModel(backend=backend, model_name="opus")
    response, _ = asyncio.run(model.request(_request(None, "x"), None, _params()))
    assert isinstance(response.parts[0], TextPart)
    assert response.parts[0].content == ""


def test_structured_path_returns_toolcallpart():
    schema = {
        "type": "object",
        "properties": {"title": {"type": "string"}, "score": {"type": "integer"}},
        "required": ["title", "score"],
    }
    output_tool = ToolDefinition(
        name="final_result",
        description="structured output",
        parameters_json_schema=schema,
    )
    payload = {"title": "x", "score": 5}
    backend = FakeBackend(
        ClaudeResult(model="opus", structured=payload, input_tokens=20, output_tokens=4)
    )
    model = ClaudeCodeModel(backend=backend, model_name="opus")

    response, usage = asyncio.run(
        model.request(_request(None, "extract"), None, _params(output_tools=[output_tool]))
    )

    assert len(response.parts) == 1
    part = response.parts[0]
    assert isinstance(part, ToolCallPart)
    assert part.tool_name == "final_result"
    assert part.args == payload

    assert usage.request_tokens == 20
    assert usage.response_tokens == 4

    # Structured path forwards the output tool's JSON schema to the backend.
    assert backend.calls[0]["schema"] == schema


def test_structured_path_falls_back_to_parsing_text():
    output_tool = ToolDefinition(
        name="final_result",
        description="structured output",
        parameters_json_schema={"type": "object"},
    )
    # No structured payload — the model must parse the JSON text instead.
    backend = FakeBackend(ClaudeResult(model="opus", text='{"k": 1}'))
    model = ClaudeCodeModel(backend=backend, model_name="opus")

    response, _ = asyncio.run(
        model.request(_request(None, "extract"), None, _params(output_tools=[output_tool]))
    )
    part = response.parts[0]
    assert isinstance(part, ToolCallPart)
    assert part.args == {"k": 1}


def test_request_stream_not_implemented():
    model = ClaudeCodeModel(
        backend=FakeBackend(ClaudeResult(model="x")), model_name="opus"
    )

    async def _drain():
        async for _ in model.request_stream(_request(None, "x"), None, _params()):
            pass

    with pytest.raises(NotImplementedError):
        asyncio.run(_drain())


def test_flatten_joins_multiple_parts():
    messages = [
        ModelRequest(
            parts=[
                SystemPromptPart(content="sys-a"),
                SystemPromptPart(content="sys-b"),
                UserPromptPart(content="user-a"),
                UserPromptPart(content="user-b"),
            ]
        )
    ]
    prompt, system = ClaudeCodeModel._flatten_messages(messages)
    assert prompt == "user-a\n\nuser-b"
    assert system == "sys-a\n\nsys-b"


def test_flatten_no_system_returns_none():
    prompt, system = ClaudeCodeModel._flatten_messages(_request(None, "only-user"))
    assert prompt == "only-user"
    assert system is None
