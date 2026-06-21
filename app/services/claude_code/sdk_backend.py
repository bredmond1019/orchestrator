"""SDK-backed Claude Code backend driving the official `claude-agent-sdk`.

`ClaudeAgentSdkBackend` implements `ClaudeCodeBackend` by calling
`claude_agent_sdk.query()` in headless mode. The spawned `claude` CLI is forced
onto the Claude Code **subscription** (not metered API credits) by blanking the
`ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` env vars for the child process, so a
key exported on the host can't redirect billing to the API. Config comes from the
`CLAUDE_CODE_*` env vars (see `app/.env.example`). The terminal `ResultMessage`
is mapped into a `ClaudeResult`; any non-`success` / error result raises a
descriptive `RuntimeError`.
"""

import asyncio
import os
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from services.claude_code.backend import ClaudeResult

_DEFAULT_TIMEOUT_SECONDS = 180.0
_DEFAULT_PERMISSION_MODE = "bypassPermissions"


class ClaudeAgentSdkBackend:
    """Run one Claude Code LLM turn via `claude_agent_sdk.query()`.

    Conforms to the `ClaudeCodeBackend` protocol. Reads host configuration from
    the `CLAUDE_CODE_*` env vars at call time so a deployment can change them
    without reconstructing the backend.
    """

    def _timeout_seconds(self) -> float:
        raw = os.getenv("CLAUDE_CODE_SDK_TIMEOUT_SECONDS")
        if not raw:
            return _DEFAULT_TIMEOUT_SECONDS
        try:
            return float(raw)
        except ValueError:
            return _DEFAULT_TIMEOUT_SECONDS

    def _build_options(
        self,
        *,
        system: str | None,
        model: str,
        schema: dict | None,
    ) -> ClaudeAgentOptions:
        cwd = os.getenv("CLAUDE_CODE_CWD") or None
        cli_path = os.getenv("CLAUDE_CODE_BIN") or None
        permission_mode = (
            os.getenv("CLAUDE_CODE_PERMISSION_MODE") or _DEFAULT_PERMISSION_MODE
        )
        output_format: dict[str, Any] | None = (
            {"type": "json_schema", "schema": schema} if schema else None
        )
        # Force subscription auth: blank any inherited API key/token so the
        # spawned CLI authenticates against the Claude Code subscription.
        env = {"ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": ""}
        return ClaudeAgentOptions(
            model=model,
            system_prompt=system,
            cwd=cwd,
            permission_mode=permission_mode,
            cli_path=cli_path,
            output_format=output_format,
            env=env,
        )

    async def run(
        self,
        prompt: str,
        *,
        system: str | None,
        model: str,
        schema: dict | None,
    ) -> ClaudeResult:
        """Execute one turn and map the terminal `ResultMessage` to `ClaudeResult`."""
        options = self._build_options(system=system, model=model, schema=schema)
        try:
            result_message = await asyncio.wait_for(
                self._drain(prompt, options), timeout=self._timeout_seconds()
            )
        except TimeoutError as e:
            raise RuntimeError(
                f"Claude Code SDK call timed out after {self._timeout_seconds()}s"
            ) from e

        if result_message is None:
            raise RuntimeError(
                "Claude Code SDK call produced no terminal ResultMessage"
            )

        if result_message.subtype != "success" or result_message.is_error:
            raise RuntimeError(
                "Claude Code SDK call failed: "
                f"subtype={result_message.subtype!r}, "
                f"is_error={result_message.is_error}, "
                f"api_error_status={result_message.api_error_status}, "
                f"errors={result_message.errors}"
            )

        usage = result_message.usage or {}
        return ClaudeResult(
            model=model,
            text=result_message.result,
            structured=result_message.structured_output,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cost_usd=result_message.total_cost_usd,
            session_id=result_message.session_id,
        )

    async def _drain(
        self, prompt: str, options: ClaudeAgentOptions
    ) -> ResultMessage | None:
        """Consume the query stream, returning the terminal `ResultMessage`."""
        terminal: ResultMessage | None = None
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, ResultMessage):
                terminal = msg
        return terminal
