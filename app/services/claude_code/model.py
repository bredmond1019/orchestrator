"""Shared pydantic-ai ``Model`` that drives a Claude Code backend.

``ClaudeCodeModel`` is the seam between pydantic-ai's ``Agent`` machinery and a
pluggable :class:`~services.claude_code.backend.ClaudeCodeBackend`. It implements
the abstract surface of the **installed** pydantic-ai 0.1.5 ``Model`` (verified by
introspection): ``request`` returns a ``tuple[ModelResponse, Usage]`` (not a bare
response), and the ``model_name`` / ``system`` / ``base_url`` properties plus
``customize_request_parameters`` / ``_get_instructions`` are all provided.

The same model is reused unchanged by the later ``CLAUDE_CODE_SESSION`` (bastion)
provider, which only swaps in a different backend implementation.
"""

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import Usage

from services.claude_code.backend import ClaudeCodeBackend


class ClaudeCodeModel(Model):
    """A pydantic-ai ``Model`` that delegates one LLM turn to a Claude Code backend.

    Constructed with a concrete ``backend`` (the SDK backend in this feature, the
    bastion session backend later) and the requested ``model_name`` (a Claude alias
    such as ``"opus"`` or a full id like ``"claude-opus-4-8"``). When the node
    declares an ``output_type`` pydantic-ai populates ``output_tools`` and the model
    returns a ``ToolCallPart`` invoking that output tool so the result is validated
    into the node's ``OutputType``; otherwise it returns a plain ``TextPart``.
    """

    def __init__(self, backend: ClaudeCodeBackend, model_name: str) -> None:
        super().__init__()
        self._backend = backend
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        """The requested Claude model name (alias or full id)."""
        return self._model_name

    @property
    def system(self) -> str:
        """Provider/system identifier surfaced to pydantic-ai telemetry."""
        return "claude-code"

    @property
    def base_url(self) -> str | None:
        """No HTTP base URL — the backend shells out to the Claude Code engine."""
        return None

    def customize_request_parameters(
        self, model_request_parameters: ModelRequestParameters
    ) -> ModelRequestParameters:
        """Return request parameters unchanged (no provider-specific rewriting)."""
        return model_request_parameters

    def _get_instructions(self, messages: list[ModelMessage]) -> str | None:
        """No model-level instruction injection; system text is read in ``request``."""
        return None

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> tuple[ModelResponse, Usage]:
        """Execute one turn via the backend and adapt it to pydantic-ai 0.1.5.

        Returns a 2-tuple ``(ModelResponse, Usage)`` as the installed pydantic-ai
        expects. Emits a ``ToolCallPart`` when structured output is requested
        (non-empty ``output_tools``) and a ``TextPart`` otherwise.
        """
        prompt, system = self._flatten_messages(messages)

        output_tools = model_request_parameters.output_tools
        if output_tools:
            output_tool = output_tools[0]
            schema = output_tool.parameters_json_schema
            result = await self._backend.run(
                prompt, system=system, model=self._model_name, schema=schema
            )
            args = result.structured
            if args is None:
                args = json.loads(result.text) if result.text else {}
            response = ModelResponse(
                parts=[ToolCallPart(tool_name=output_tool.name, args=args)]
            )
        else:
            result = await self._backend.run(
                prompt, system=system, model=self._model_name, schema=None
            )
            response = ModelResponse(parts=[TextPart(content=result.text or "")])

        usage = Usage(
            requests=1,
            request_tokens=result.input_tokens,
            response_tokens=result.output_tokens,
        )
        return response, usage

    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> AsyncIterator[StreamedResponse]:
        """Streaming is out of scope for the Claude Code provider (future work)."""
        raise NotImplementedError(
            "ClaudeCodeModel does not support streaming; use request() instead "
            "(streaming is a documented future item)."
        )
        # Unreachable: present only so this stays an async generator for the ABC.
        yield  # pylint: disable=unreachable  # pragma: no cover

    @staticmethod
    def _flatten_messages(
        messages: list[ModelMessage],
    ) -> tuple[str, str | None]:
        """Collapse the message history into one user prompt + system text.

        Reads ``ModelRequest`` parts: ``SystemPromptPart`` content becomes the
        system string, ``UserPromptPart`` content becomes the prompt. Multiple
        parts are joined with blank lines so multi-part requests survive.
        """
        prompts: list[str] = []
        systems: list[str] = []
        for message in messages:
            if not isinstance(message, ModelRequest):
                continue
            for part in message.parts:
                if isinstance(part, SystemPromptPart):
                    systems.append(part.content)
                elif isinstance(part, UserPromptPart):
                    prompts.append(ClaudeCodeModel._render_content(part.content))

        prompt = "\n\n".join(p for p in prompts if p)
        system = "\n\n".join(s for s in systems if s) or None
        return prompt, system

    @staticmethod
    def _render_content(content: Any) -> str:
        """Render a user-prompt part's content (str or sequence) to plain text."""
        if isinstance(content, str):
            return content
        if isinstance(content, Sequence):
            return "\n\n".join(
                item if isinstance(item, str) else str(item) for item in content
            )
        return str(content)
