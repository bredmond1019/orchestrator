"""Backend protocol + result type for the Claude Code LLM provider.

`ClaudeCodeBackend` is the pluggable seam that `ClaudeCodeModel` (a pydantic-ai
`Model`) delegates to. This task ships the contract only; concrete backends
(`ClaudeAgentSdkBackend`, and later the bastion session backend) implement it.
`ClaudeResult` is the uniform return shape every backend produces, carrying the
text/structured payload plus the real token usage and cost the SDK reports.
"""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class ClaudeResult:
    """One LLM turn's output from a Claude Code backend.

    `text` and `structured` are mutually exclusive in practice: a free-text run
    populates `text`, a structured-output run (a JSON schema was requested)
    populates `structured`. Token counts and cost come straight from the SDK's
    terminal `ResultMessage` and may be `None` if the backend can't report them.
    """

    model: str
    text: str | None = None
    structured: Any | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    session_id: str | None = None


@runtime_checkable
class ClaudeCodeBackend(Protocol):
    """A pluggable backend that drives one Claude Code LLM call.

    `schema` is a JSON schema for structured output, or `None` for free text.
    Implementations run the underlying Claude Code engine (the official
    `claude-agent-sdk`, or a bastion session) and map its result into a
    `ClaudeResult`.
    """

    async def run(
        self,
        prompt: str,
        *,
        system: str | None,
        model: str,
        schema: dict | None,
    ) -> ClaudeResult:
        """Execute one turn and return its `ClaudeResult`."""
