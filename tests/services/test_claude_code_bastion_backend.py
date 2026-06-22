"""Unit tests for BastionSessionBackend (prompt file, flags, parsing, errors)."""

import asyncio
import json
import subprocess

import pytest
from services.claude_code import BastionSessionBackend, ClaudeResult


def _configure_env(monkeypatch, io_dir):
    """Point the backend at a tmp io/work dir and a fake bastion on PATH."""
    monkeypatch.setenv("BASTION_BIN", "/usr/local/bin/bastion")
    monkeypatch.setenv("CLAUDE_CODE_TMUX_SESSION", "orchestrator-claude")
    monkeypatch.setenv("CLAUDE_CODE_WORKDIR", str(io_dir))
    monkeypatch.setenv("CLAUDE_CODE_IO_DIR", str(io_dir))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_TIMEOUT_SECONDS", "180")


def _install_fake_run(monkeypatch, *, captured, answer=None, returncode=0,
                      raise_timeout=False, stderr=""):
    """Patch `subprocess.run`; optionally write the answer file the CLI would."""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        # The prompt file should already be written by the time the CLI runs.
        prompt_idx = cmd.index("--prompt-file") + 1
        captured["prompt_contents"] = (
            open(cmd[prompt_idx], encoding="utf-8").read()
        )
        if raise_timeout:
            raise subprocess.TimeoutExpired(
                cmd=cmd, timeout=1, stderr=stderr
            )
        if answer is not None:
            out_idx = cmd.index("--out") + 1
            with open(cmd[out_idx], "w", encoding="utf-8") as fh:
                fh.write(answer)
        return subprocess.CompletedProcess(
            args=cmd, returncode=returncode, stdout="", stderr=stderr
        )

    monkeypatch.setattr("services.claude_code.bastion_backend.subprocess.run",
                        fake_run)


class TestPromptFileAndFlags:
    def test_invokes_bastion_ask_with_pinned_flags(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        _install_fake_run(monkeypatch, captured=captured, answer="hi")
        backend = BastionSessionBackend()

        asyncio.run(
            backend.run("do it", system=None, model="opus", schema=None)
        )

        cmd = captured["cmd"]
        assert cmd[0] == "/usr/local/bin/bastion"
        assert cmd[1] == "ask"
        assert "--session" in cmd
        assert cmd[cmd.index("--session") + 1] == "orchestrator-claude"
        assert "--prompt-file" in cmd
        assert "--out" in cmd
        assert cmd[cmd.index("--dir") + 1] == str(tmp_path)
        assert cmd[cmd.index("--timeout") + 1] == "180"
        kwargs = captured["kwargs"]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] > 180

    def test_prompt_file_contains_system_and_prompt(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        _install_fake_run(monkeypatch, captured=captured, answer="ok")
        backend = BastionSessionBackend()

        asyncio.run(
            backend.run("the prompt", system="be terse", model="opus",
                        schema=None)
        )

        contents = captured["prompt_contents"]
        assert "be terse" in contents
        assert "the prompt" in contents

    def test_schema_writes_json_instruction(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        _install_fake_run(monkeypatch, captured=captured, answer="{}")
        backend = BastionSessionBackend()
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}

        asyncio.run(
            backend.run("p", system=None, model="opus", schema=schema)
        )

        contents = captured["prompt_contents"]
        assert "JSON object conforming to this schema" in contents
        assert json.dumps(schema) in contents
        # structured request -> .json out file
        assert captured["cmd"][captured["cmd"].index("--out") + 1].endswith(
            ".json"
        )

    def test_free_text_uses_md_out_file(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        _install_fake_run(monkeypatch, captured=captured, answer="ok")
        backend = BastionSessionBackend()

        asyncio.run(backend.run("p", system=None, model="opus", schema=None))

        assert captured["cmd"][captured["cmd"].index("--out") + 1].endswith(
            ".md"
        )


class TestResultParsing:
    def test_free_text_returns_markdown_as_text(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        _install_fake_run(monkeypatch, captured=captured, answer="hello world")
        backend = BastionSessionBackend()

        result = asyncio.run(
            backend.run("p", system=None, model="claude-opus-4-8", schema=None)
        )

        assert isinstance(result, ClaudeResult)
        assert result.text == "hello world"
        assert result.structured is None
        assert result.model == "claude-opus-4-8"

    def test_structured_returns_parsed_json(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        payload = {"title": "T", "score": 9}
        _install_fake_run(
            monkeypatch, captured=captured, answer=json.dumps(payload)
        )
        backend = BastionSessionBackend()

        result = asyncio.run(
            backend.run("p", system=None, model="opus",
                        schema={"type": "object"})
        )

        assert result.structured == payload
        assert result.text == json.dumps(payload)

    def test_tokens_and_cost_are_none(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        _install_fake_run(monkeypatch, captured=captured, answer="ok")
        backend = BastionSessionBackend()

        result = asyncio.run(
            backend.run("p", system=None, model="opus", schema=None)
        )

        assert result.input_tokens is None
        assert result.output_tokens is None
        assert result.cost_usd is None
        assert result.session_id is None


class TestErrorHandling:
    def test_nonzero_exit_raises_with_stderr(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        _install_fake_run(
            monkeypatch, captured=captured, answer="ok", returncode=2,
            stderr="bastion: session not found",
        )
        backend = BastionSessionBackend()

        with pytest.raises(RuntimeError) as excinfo:
            asyncio.run(
                backend.run("p", system=None, model="opus", schema=None)
            )
        assert "session not found" in str(excinfo.value)

    def test_missing_answer_file_raises_with_stderr(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        # answer=None -> CLI "succeeds" but writes no file.
        _install_fake_run(
            monkeypatch, captured=captured, answer=None, returncode=0,
            stderr="warn: nothing written",
        )
        backend = BastionSessionBackend()

        with pytest.raises(RuntimeError) as excinfo:
            asyncio.run(
                backend.run("p", system=None, model="opus", schema=None)
            )
        assert "no answer file" in str(excinfo.value)
        assert "nothing written" in str(excinfo.value)

    def test_timeout_raises_with_stderr(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        _install_fake_run(
            monkeypatch, captured=captured, raise_timeout=True,
            stderr="timed out waiting",
        )
        backend = BastionSessionBackend()

        with pytest.raises(RuntimeError) as excinfo:
            asyncio.run(
                backend.run("p", system=None, model="opus", schema=None)
            )
        assert "timed out" in str(excinfo.value)

    def test_invalid_json_for_structured_raises(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        _install_fake_run(monkeypatch, captured=captured, answer="not json")
        backend = BastionSessionBackend()

        with pytest.raises(RuntimeError) as excinfo:
            asyncio.run(
                backend.run("p", system=None, model="opus",
                            schema={"type": "object"})
            )
        assert "not valid JSON" in str(excinfo.value)

    def test_missing_workdir_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BASTION_BIN", "/usr/local/bin/bastion")
        monkeypatch.delenv("CLAUDE_CODE_WORKDIR", raising=False)
        backend = BastionSessionBackend()

        with pytest.raises(RuntimeError) as excinfo:
            asyncio.run(
                backend.run("p", system=None, model="opus", schema=None)
            )
        assert "CLAUDE_CODE_WORKDIR" in str(excinfo.value)


class TestCleanup:
    def test_temp_files_removed_on_success(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        _install_fake_run(monkeypatch, captured=captured, answer="ok")
        backend = BastionSessionBackend()

        asyncio.run(backend.run("p", system=None, model="opus", schema=None))

        assert list(tmp_path.glob("prompt-*.md")) == []
        assert list(tmp_path.glob("out-*.md")) == []

    def test_temp_files_removed_on_error(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        captured: dict = {}
        _install_fake_run(
            monkeypatch, captured=captured, answer="ok", returncode=1,
            stderr="boom",
        )
        backend = BastionSessionBackend()

        with pytest.raises(RuntimeError):
            asyncio.run(
                backend.run("p", system=None, model="opus", schema=None)
            )

        assert list(tmp_path.glob("prompt-*.md")) == []
        assert list(tmp_path.glob("out-*")) == []


class TestBinaryResolution:
    def test_missing_bastion_raises(self, monkeypatch, tmp_path):
        _configure_env(monkeypatch, tmp_path)
        monkeypatch.delenv("BASTION_BIN", raising=False)
        monkeypatch.setattr(
            "services.claude_code.bastion_backend.shutil.which",
            lambda name: None,
        )
        backend = BastionSessionBackend()

        with pytest.raises(RuntimeError) as excinfo:
            asyncio.run(
                backend.run("p", system=None, model="opus", schema=None)
            )
        assert "bastion binary not found" in str(excinfo.value)
