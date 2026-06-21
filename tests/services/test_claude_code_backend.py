"""Unit tests for the Claude Code backend contract (ClaudeResult + protocol)."""

import asyncio
from dataclasses import fields

import pytest
from services.claude_code import ClaudeCodeBackend, ClaudeResult


class TestClaudeResult:
    def test_minimal_construction_defaults(self):
        result = ClaudeResult(model="claude-opus-4-8")
        assert result.model == "claude-opus-4-8"
        assert result.text is None
        assert result.structured is None
        assert result.input_tokens is None
        assert result.output_tokens is None
        assert result.cost_usd is None
        assert result.session_id is None

    def test_text_payload(self):
        result = ClaudeResult(
            model="opus",
            text="hello",
            input_tokens=12,
            output_tokens=3,
            cost_usd=0.0,
            session_id="sess-1",
        )
        assert result.text == "hello"
        assert result.structured is None
        assert result.input_tokens == 12
        assert result.output_tokens == 3
        assert result.cost_usd == 0.0
        assert result.session_id == "sess-1"

    def test_structured_payload(self):
        payload = {"title": "x", "score": 5}
        result = ClaudeResult(model="opus", structured=payload)
        assert result.structured == payload
        assert result.text is None

    def test_field_set_matches_contract(self):
        names = {f.name for f in fields(ClaudeResult)}
        assert names == {
            "model",
            "text",
            "structured",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "session_id",
        }

    def test_model_is_required(self):
        with pytest.raises(TypeError):
            ClaudeResult()  # type: ignore[call-arg]


class TestClaudeCodeBackendProtocol:
    def test_runtime_checkable_accepts_conforming_backend(self):
        class FakeBackend:
            async def run(self, prompt, *, system, model, schema):
                return ClaudeResult(model=model, text=prompt)

        assert isinstance(FakeBackend(), ClaudeCodeBackend)

    def test_runtime_checkable_rejects_non_conforming(self):
        class NotABackend:
            pass

        assert not isinstance(NotABackend(), ClaudeCodeBackend)

    def test_conforming_backend_returns_claude_result(self):
        class FakeBackend:
            async def run(self, prompt, *, system, model, schema):
                return ClaudeResult(model=model, text=f"{system}:{prompt}:{schema}")

        backend: ClaudeCodeBackend = FakeBackend()
        result = asyncio.run(
            backend.run("p", system="s", model="claude-opus-4-8", schema=None)
        )
        assert isinstance(result, ClaudeResult)
        assert result.model == "claude-opus-4-8"
        assert result.text == "s:p:None"
