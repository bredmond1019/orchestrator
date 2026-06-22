"""Bastion-session-backed Claude Code backend driving `bastion ask`.

`BastionSessionBackend` implements `ClaudeCodeBackend` by shelling out to the
external `bastion ask` command, which sends one turn into the live interactive
Claude Code tmux session that `bastion` manages and waits for the answer file.
Because the turn runs in the real session it is subscription-billed AND
observable/attachable in `bastion sessions`. A file-based protocol is used: the
prompt (plus a JSON-schema instruction when structured output is requested) is
written to a prompt file, `bastion ask` is invoked with the pinned v0.1.0 flags,
and the answer file is read back and parsed. Config comes from the
`CLAUDE_CODE_*` / `BASTION_*` env vars (see `app/.env.example`). Session mode
cannot report token usage or cost, so those fields are always `None`.
"""

import asyncio
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from services.claude_code.backend import ClaudeResult

_DEFAULT_SESSION = "orchestrator-claude"
_DEFAULT_TIMEOUT_SECONDS = 180
_TIMEOUT_BUFFER_SECONDS = 30


class BastionSessionBackend:
    """Run one Claude Code LLM turn via the external `bastion ask` command.

    Conforms to the `ClaudeCodeBackend` protocol. Reads host configuration from
    the `BASTION_*` / `CLAUDE_CODE_*` env vars at call time so a deployment can
    change them without reconstructing the backend.
    """

    def _resolve_bastion(self) -> str:
        configured = os.getenv("BASTION_BIN")
        if configured:
            resolved = shutil.which(configured) or configured
            return resolved
        found = shutil.which("bastion")
        if not found:
            raise RuntimeError(
                "bastion binary not found: set BASTION_BIN or put `bastion` on PATH"
            )
        return found

    def _session(self) -> str:
        return os.getenv("CLAUDE_CODE_TMUX_SESSION") or _DEFAULT_SESSION

    def _workdir(self) -> str:
        workdir = os.getenv("CLAUDE_CODE_WORKDIR")
        if not workdir:
            raise RuntimeError(
                "CLAUDE_CODE_WORKDIR is required for session mode "
                "(a Claude-trusted scratch dir used to create the session)"
            )
        return workdir

    def _io_dir(self) -> str:
        return os.getenv("CLAUDE_CODE_IO_DIR") or self._workdir()

    def _timeout_seconds(self) -> int:
        raw = os.getenv("CLAUDE_CODE_SESSION_TIMEOUT_SECONDS")
        if not raw:
            return _DEFAULT_TIMEOUT_SECONDS
        try:
            return int(raw)
        except ValueError:
            return _DEFAULT_TIMEOUT_SECONDS

    def _build_prompt(
        self, prompt: str, *, system: str | None, schema: dict | None
    ) -> str:
        parts: list[str] = []
        if system:
            parts.append(system)
        parts.append(prompt)
        if schema is not None:
            parts.append(
                "Write ONLY a JSON object conforming to this schema: "
                + json.dumps(schema)
            )
        return "\n\n".join(parts)

    async def run(
        self,
        prompt: str,
        *,
        system: str | None,
        model: str,
        schema: dict | None,
    ) -> ClaudeResult:
        """Drive one turn through `bastion ask` and map the answer file to `ClaudeResult`."""
        io_dir = Path(self._io_dir())
        turn_id = uuid.uuid4().hex
        prompt_path = io_dir / f"prompt-{turn_id}.md"
        out_path = io_dir / (
            f"out-{turn_id}.json" if schema is not None else f"out-{turn_id}.md"
        )
        try:
            prompt_path.write_text(
                self._build_prompt(prompt, system=system, schema=schema),
                encoding="utf-8",
            )
            completed = await self._ask(prompt_path, out_path)
            if completed.returncode != 0:
                raise RuntimeError(
                    "`bastion ask` exited with "
                    f"code {completed.returncode}: {completed.stderr}"
                )
            if not out_path.exists():
                raise RuntimeError(
                    "`bastion ask` produced no answer file at "
                    f"{out_path}: {completed.stderr}"
                )
            return self._parse_answer(out_path, schema=schema, model=model)
        finally:
            for path in (prompt_path, out_path):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    async def _ask(
        self, prompt_path: Path, out_path: Path
    ) -> subprocess.CompletedProcess:
        """Invoke `bastion ask` off-loop; raise on timeout with stderr included."""
        timeout = self._timeout_seconds()
        cmd = [
            self._resolve_bastion(),
            "ask",
            "--session",
            self._session(),
            "--prompt-file",
            str(prompt_path),
            "--out",
            str(out_path),
            "--dir",
            self._workdir(),
            "--timeout",
            str(timeout),
        ]
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None, lambda: self._invoke(cmd, timeout)
            )
        except subprocess.TimeoutExpired as e:
            stderr = e.stderr if isinstance(e.stderr, str) else ""
            raise RuntimeError(
                f"`bastion ask` timed out after {timeout}s: {stderr}"
            ) from e

    def _parse_answer(
        self, out_path: Path, *, schema: dict | None, model: str
    ) -> ClaudeResult:
        """Read the answer file into a `ClaudeResult` (JSON when structured)."""
        raw = out_path.read_text(encoding="utf-8")
        structured: Any | None = None
        if schema is not None:
            try:
                structured = json.loads(raw)
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    "`bastion ask` answer file was not valid JSON for a "
                    f"structured request: {e}"
                ) from e
        return ClaudeResult(
            model=model,
            text=raw,
            structured=structured,
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
            session_id=None,
        )

    def _invoke(
        self, cmd: list[str], timeout: int
    ) -> subprocess.CompletedProcess:
        """Run the blocking `bastion ask` subprocess (executed in a thread)."""
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + _TIMEOUT_BUFFER_SECONDS,
            check=False,
        )
