"""ToolUseNode — abstract base for raw Anthropic SDK tool-use loops."""

import logging
import os
from abc import abstractmethod

import anthropic

from core.nodes.base import Node
from core.task import TaskContext

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"


class ToolUseNode(Node):
    """Abstract node that runs a raw Anthropic SDK tool-use loop.

    Subclasses define the ``tools`` they expose and implement
    ``handle_tool_call`` to execute each tool. ``process`` drives the
    request/tool-result loop, bounded by ``max_iterations`` so it can never
    run forever. The model is injected via ``TOOL_USE_MODEL`` (never
    hardcoded), keeping deployment choices out of the node.
    """

    max_iterations: int = 10

    def __init__(self) -> None:
        self._client = anthropic.Anthropic()
        self._model = os.getenv("TOOL_USE_MODEL", _DEFAULT_MODEL)

    @property
    @abstractmethod
    def tools(self) -> list[dict]:
        """Anthropic tool definitions for this node."""

    @abstractmethod
    def handle_tool_call(
        self,
        tool_name: str,
        tool_input: dict,
        task_context: TaskContext,
    ) -> str:
        """Execute a single tool call and return the result string."""

    def _build_initial_messages(self, task_context: TaskContext) -> list[dict]:
        """Override to customise the initial user message for the loop."""
        return [{"role": "user", "content": str(task_context.nodes)}]

    def process(self, task_context: TaskContext) -> TaskContext:
        messages: list[dict] = self._build_initial_messages(task_context)
        iterations = 0
        input_tokens = 0
        output_tokens = 0

        while iterations < self.max_iterations:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                tools=self.tools,
                messages=messages,
            )
            iterations += 1

            usage = getattr(response, "usage", None)
            if usage is not None:
                input_tokens += getattr(usage, "input_tokens", 0) or 0
                output_tokens += getattr(usage, "output_tokens", 0) or 0

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self.handle_tool_call(
                            block.name, block.input, task_context
                        )
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                break

        if iterations >= self.max_iterations:
            log.warning(
                "ToolUseNode %s hit max_iterations=%d; returning partial result",
                self.node_name,
                self.max_iterations,
            )

        run = task_context.node_runs.get(self.node_name)
        if run is not None:
            run.usage = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model": self._model,
            }

        return task_context
