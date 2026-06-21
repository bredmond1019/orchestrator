"""Unit tests for ClaudeAgentSdkBackend (mapping, env scrub, error handling)."""

import asyncio

import pytest
from claude_agent_sdk import ResultMessage
from services.claude_code import ClaudeResult
from services.claude_code.sdk_backend import ClaudeAgentSdkBackend


def _make_result(**overrides) -> ResultMessage:
    """Build a ResultMessage with sensible success defaults."""
    base = {
        "subtype": "success",
        "duration_ms": 10,
        "duration_api_ms": 8,
        "is_error": False,
        "num_turns": 1,
        "session_id": "sess-abc",
        "total_cost_usd": 0.0,
        "usage": {"input_tokens": 42, "output_tokens": 7},
        "result": "hello world",
        "structured_output": None,
    }
    base.update(overrides)
    return ResultMessage(**base)


def _install_fake_query(monkeypatch, *, result_message, captured: dict):
    """Patch the module-local `query` with a fake async generator."""

    async def fake_query(*, prompt, options):
        captured["prompt"] = prompt
        captured["options"] = options
        for msg in (result_message,):
            yield msg

    monkeypatch.setattr(
        "services.claude_code.sdk_backend.query", fake_query
    )


class TestOptionBuilding:
    def test_options_carry_model_system_and_output_format(self, monkeypatch):
        captured: dict = {}
        _install_fake_query(
            monkeypatch, result_message=_make_result(), captured=captured
        )
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        backend = ClaudeAgentSdkBackend()

        asyncio.run(
            backend.run(
                "do the thing",
                system="be terse",
                model="claude-opus-4-8",
                schema=schema,
            )
        )

        options = captured["options"]
        assert captured["prompt"] == "do the thing"
        assert options.model == "claude-opus-4-8"
        assert options.system_prompt == "be terse"
        assert options.output_format == {
            "type": "json_schema",
            "schema": schema,
        }

    def test_no_schema_means_no_output_format(self, monkeypatch):
        captured: dict = {}
        _install_fake_query(
            monkeypatch, result_message=_make_result(), captured=captured
        )
        backend = ClaudeAgentSdkBackend()

        asyncio.run(
            backend.run("p", system=None, model="opus", schema=None)
        )

        assert captured["options"].output_format is None

    def test_env_blanks_anthropic_api_key(self, monkeypatch):
        captured: dict = {}
        _install_fake_query(
            monkeypatch, result_message=_make_result(), captured=captured
        )
        backend = ClaudeAgentSdkBackend()

        asyncio.run(backend.run("p", system=None, model="opus", schema=None))

        env = captured["options"].env
        assert env["ANTHROPIC_API_KEY"] == ""
        assert env["ANTHROPIC_AUTH_TOKEN"] == ""

    def test_permission_mode_and_paths_from_env(self, monkeypatch):
        captured: dict = {}
        _install_fake_query(
            monkeypatch, result_message=_make_result(), captured=captured
        )
        monkeypatch.setenv("CLAUDE_CODE_PERMISSION_MODE", "acceptEdits")
        monkeypatch.setenv("CLAUDE_CODE_CWD", "/tmp/wd")
        monkeypatch.setenv("CLAUDE_CODE_BIN", "/usr/local/bin/claude")
        backend = ClaudeAgentSdkBackend()

        asyncio.run(backend.run("p", system=None, model="opus", schema=None))

        options = captured["options"]
        assert options.permission_mode == "acceptEdits"
        assert options.cwd == "/tmp/wd"
        assert options.cli_path == "/usr/local/bin/claude"

    def test_permission_mode_defaults_when_unset(self, monkeypatch):
        captured: dict = {}
        _install_fake_query(
            monkeypatch, result_message=_make_result(), captured=captured
        )
        monkeypatch.delenv("CLAUDE_CODE_PERMISSION_MODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_CWD", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)
        backend = ClaudeAgentSdkBackend()

        asyncio.run(backend.run("p", system=None, model="opus", schema=None))

        options = captured["options"]
        assert options.permission_mode == "bypassPermissions"
        assert options.cwd is None
        assert options.cli_path is None


class TestResultMapping:
    def test_text_result_maps_into_claude_result(self, monkeypatch):
        captured: dict = {}
        _install_fake_query(
            monkeypatch,
            result_message=_make_result(
                result="the answer",
                usage={"input_tokens": 100, "output_tokens": 25},
                total_cost_usd=0.0,
                session_id="sess-xyz",
            ),
            captured=captured,
        )
        backend = ClaudeAgentSdkBackend()

        result = asyncio.run(
            backend.run("p", system=None, model="claude-opus-4-8", schema=None)
        )

        assert isinstance(result, ClaudeResult)
        assert result.text == "the answer"
        assert result.structured is None
        assert result.input_tokens == 100
        assert result.output_tokens == 25
        assert result.cost_usd == 0.0
        assert result.session_id == "sess-xyz"
        assert result.model == "claude-opus-4-8"

    def test_structured_output_maps_into_claude_result(self, monkeypatch):
        payload = {"title": "T", "score": 9}
        captured: dict = {}
        _install_fake_query(
            monkeypatch,
            result_message=_make_result(
                result=None, structured_output=payload
            ),
            captured=captured,
        )
        backend = ClaudeAgentSdkBackend()

        result = asyncio.run(
            backend.run(
                "p", system=None, model="opus", schema={"type": "object"}
            )
        )

        assert result.structured == payload
        assert result.text is None

    def test_missing_usage_yields_none_tokens(self, monkeypatch):
        captured: dict = {}
        _install_fake_query(
            monkeypatch,
            result_message=_make_result(usage=None),
            captured=captured,
        )
        backend = ClaudeAgentSdkBackend()

        result = asyncio.run(
            backend.run("p", system=None, model="opus", schema=None)
        )

        assert result.input_tokens is None
        assert result.output_tokens is None


class TestErrorHandling:
    def test_non_success_subtype_raises(self, monkeypatch):
        captured: dict = {}
        _install_fake_query(
            monkeypatch,
            result_message=_make_result(
                subtype="error_max_turns",
                is_error=True,
                result=None,
                errors=["hit max turns"],
            ),
            captured=captured,
        )
        backend = ClaudeAgentSdkBackend()

        with pytest.raises(RuntimeError) as excinfo:
            asyncio.run(
                backend.run("p", system=None, model="opus", schema=None)
            )
        assert "error_max_turns" in str(excinfo.value)
        assert "hit max turns" in str(excinfo.value)

    def test_success_subtype_but_is_error_raises(self, monkeypatch):
        captured: dict = {}
        _install_fake_query(
            monkeypatch,
            result_message=_make_result(
                subtype="success",
                is_error=True,
                api_error_status=529,
            ),
            captured=captured,
        )
        backend = ClaudeAgentSdkBackend()

        with pytest.raises(RuntimeError) as excinfo:
            asyncio.run(
                backend.run("p", system=None, model="opus", schema=None)
            )
        assert "529" in str(excinfo.value)

    def test_no_terminal_result_raises(self, monkeypatch):
        captured: dict = {}

        async def empty_query(*, prompt, options):
            captured["called"] = True
            if False:  # pragma: no cover - never yields
                yield None

        monkeypatch.setattr(
            "services.claude_code.sdk_backend.query", empty_query
        )
        backend = ClaudeAgentSdkBackend()

        with pytest.raises(RuntimeError) as excinfo:
            asyncio.run(
                backend.run("p", system=None, model="opus", schema=None)
            )
        assert "no terminal ResultMessage" in str(excinfo.value)
