"""WrapUpNode — generates the end-of-run log entry, report, and status update.

Agent node (extends ``AgentNode``, Sonnet-tier model via the ``ANTHROPIC``
provider). Reads the current ``SDLCState`` telemetry (tasks passed/failed,
total attempts) and asks the model to produce three text artifacts: a dated
``log.md`` entry, a short markdown report, and a suggested ``status.md``
update. This node does not write any files itself — it returns the text for
a human (or a later node) to apply; see the module-level ``OutputType`` for
the exact fields.

Output: ``result = {"log_entry": str, "report": str, "status_suggestion": str}``.
"""

# The AgentConfig boilerplate + run_agent_recorded call every AgentNode
# subclass repeats trips R0801 against sibling nodes; it is the prescribed
# framework pattern, not a refactor target.
# pylint: disable=duplicate-code

import json

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from schemas.sdlc_schema import SDLCState
from services.prompt_loader import PromptManager


class WrapUpNode(AgentNode):
    """Agent node that summarizes a completed (or bailed) SDLC run."""

    class OutputType(AgentNode.OutputType):
        """Structured wrap-up artifacts emitted by the model."""

        log_entry: str
        report: str
        status_suggestion: str

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager.get_prompt(
                "sdlc_wrap_up",
                spec_slug="",  # placeholder — real values threaded via the user prompt
                tasks_passed=0,
                tasks_failed=0,
                total_attempts=0,
            ),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.ANTHROPIC,
            model_name="claude-sonnet-5",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Summarize the run's telemetry into a log entry, report, and status update.

        Reads:
          - The most recent SDLC state (``UpdateTaskStatusNode`` output if
            present, else ``LoadTaskStateNode``) for ``spec_slug`` and
            ``telemetry``.

        Writes:
          - ``WrapUpNode`` result: ``log_entry``, ``report``, ``status_suggestion``
        """
        state = SDLCState.model_validate(self._latest_state_dict(task_context))
        telemetry = state.telemetry

        rendered_system_prompt = PromptManager.get_prompt(
            "sdlc_wrap_up",
            spec_slug=state.spec_slug,
            tasks_passed=telemetry.tasks_passed,
            tasks_failed=telemetry.tasks_failed,
            total_attempts=telemetry.total_attempts,
        )
        self.agent._system_prompts = (rendered_system_prompt,)  # pylint: disable=protected-access

        user_prompt = json.dumps(
            {
                "spec_slug": state.spec_slug,
                "tasks_passed": telemetry.tasks_passed,
                "tasks_failed": telemetry.tasks_failed,
                "total_attempts": telemetry.total_attempts,
            },
            default=str,
        )

        result = self.run_agent_recorded(task_context, user_prompt)
        raw = result.output

        task_context.update_node(
            node_name=self.node_name,
            result={
                "log_entry": raw.log_entry,
                "report": raw.report,
                "status_suggestion": raw.status_suggestion,
            },
        )
        return task_context

    @staticmethod
    def _latest_state_dict(task_context: TaskContext) -> dict:
        """Return the most recently mutated state, falling back to the initial load."""
        if "UpdateTaskStatusNode" in task_context.nodes:
            return task_context.get_node_output("UpdateTaskStatusNode")["result"]
        return task_context.get_node_output("LoadTaskStateNode")["result"]
