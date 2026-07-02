"""WrapUpNode — generates the end-of-run log entry, report, and status update.

Deterministic node (no LLM). The input is purely the run's telemetry counters
(tasks passed/failed, total attempts) plus the ``spec_slug`` — there is no
prose to summarize, only counts to format — so the three text artifacts are
rendered from Jinja document templates (``sdlc_wrap_up_log`` /
``sdlc_wrap_up_report`` / ``sdlc_wrap_up_status``) via ``PromptManager`` rather
than by a model. This node does not write any files itself — it returns the
text for a human (or a later node) to apply.

Output: ``result = {"log_entry": str, "report": str, "status_suggestion": str}``.
"""

import datetime
import logging

from core.nodes.base import Node
from core.task import TaskContext
from schemas.sdlc_schema import SDLCState
from services.prompt_loader import PromptManager

logger = logging.getLogger(__name__)


class WrapUpNode(Node):
    """Render a completed (or bailed) SDLC run's wrap-up artifacts from templates."""

    def process(self, task_context: TaskContext) -> TaskContext:
        """Format the run's telemetry into a log entry, report, and status update.

        Reads:
          - The most recent SDLC state (``UpdateTaskStatusNode`` output if
            present, else ``LoadTaskStateNode``) for ``spec_slug`` and
            ``telemetry``.

        Writes:
          - ``WrapUpNode`` result: ``log_entry``, ``report``, ``status_suggestion``
        """
        state = SDLCState.model_validate(self._latest_state_dict(task_context))
        telemetry = state.telemetry

        outcome = "PASS" if telemetry.tasks_failed == 0 else "PARTIAL/FAIL"
        template_vars = {
            "spec_slug": state.spec_slug,
            "date": datetime.date.today().isoformat(),
            "tasks_passed": telemetry.tasks_passed,
            "tasks_failed": telemetry.tasks_failed,
            "total_attempts": telemetry.total_attempts,
            "outcome": outcome,
        }

        log_entry = PromptManager.get_prompt("sdlc_wrap_up_log", **template_vars).strip()
        report = PromptManager.get_prompt("sdlc_wrap_up_report", **template_vars).strip()
        status_suggestion = PromptManager.get_prompt(
            "sdlc_wrap_up_status", **template_vars
        ).strip()

        logger.info(
            "WrapUpNode: spec=%s outcome=%s passed=%s failed=%s",
            state.spec_slug,
            outcome,
            telemetry.tasks_passed,
            telemetry.tasks_failed,
        )

        task_context.update_node(
            node_name=self.node_name,
            result={
                "log_entry": log_entry,
                "report": report,
                "status_suggestion": status_suggestion,
            },
        )
        return task_context

    @staticmethod
    def _latest_state_dict(task_context: TaskContext) -> dict:
        """Return the most recently mutated state, falling back to the initial load."""
        if "UpdateTaskStatusNode" in task_context.nodes:
            return task_context.get_node_output("UpdateTaskStatusNode")["result"]
        return task_context.get_node_output("LoadTaskStateNode")["result"]
