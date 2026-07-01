"""UpdateTaskStatusNode — mutates a single task's status in the SDLC state.

Deterministic node (no LLM). Reads ``current_task_id`` from
``TaskQueueRouterNode``'s output and the failure-classification ``verdict``
from ``TriageTaskNode``'s output, locates the matching ``SDLCTask`` in the
durable ``SDLCState``, and mutates its ``status`` (and, for a retry,
``attempt_count``) accordingly. Telemetry counters on ``SDLCState.telemetry``
are updated in lockstep.

Verdict → status mapping:
    ``PASS``        → task ``DONE``,   ``telemetry.tasks_passed`` += 1
    ``MAJOR_BAIL``  → task ``FAILED``, ``telemetry.tasks_failed`` += 1
    ``RETRYABLE``   → task status unchanged (the loop retries), but
                      ``task.attempt_count`` += 1

``telemetry.total_attempts`` is incremented on every call regardless of
verdict.

The current state is read from ``UpdateTaskStatusNode``'s own prior output if
this is not the first loop iteration (so the mutation is cumulative across
the task loop), falling back to ``LoadTaskStateNode`` on the first pass.

Output: ``result = SDLCState.model_dump()`` (with the mutated task + telemetry).
"""

import logging

from core.nodes.base import Node
from core.task import TaskContext
from schemas.sdlc_schema import SDLCState, SDLCTaskStatus, SDLCTriageVerdict

logger = logging.getLogger(__name__)


class UpdateTaskStatusNode(Node):
    """Mutate the current task's status + telemetry counters in ``SDLCState``."""

    def process(self, task_context: TaskContext) -> TaskContext:
        current_task_id = task_context.get_node_output("TaskQueueRouterNode")["result"][
            "current_task_id"
        ]
        verdict = task_context.get_node_output("TriageTaskNode")["result"]["verdict"]

        state = SDLCState.model_validate(self._latest_state_dict(task_context))

        task = next((t for t in state.tasks if t.task_id == current_task_id), None)
        if task is None:
            raise ValueError(
                f"UpdateTaskStatusNode: no task with task_id={current_task_id} "
                f"found in state for spec '{state.spec_slug}'"
            )

        if verdict == SDLCTriageVerdict.PASS:
            task.status = SDLCTaskStatus.DONE
            state.telemetry.tasks_passed += 1
        elif verdict == SDLCTriageVerdict.MAJOR_BAIL:
            task.status = SDLCTaskStatus.FAILED
            state.telemetry.tasks_failed += 1
        elif verdict == SDLCTriageVerdict.RETRYABLE:
            task.attempt_count += 1
        else:
            raise ValueError(f"UpdateTaskStatusNode: unknown triage verdict {verdict!r}")

        state.telemetry.total_attempts += 1

        logger.info(
            "UpdateTaskStatusNode: task_id=%s verdict=%s status=%s",
            current_task_id,
            verdict,
            task.status,
        )

        task_context.update_node(node_name=self.node_name, result=state.model_dump())
        return task_context

    @staticmethod
    def _latest_state_dict(task_context: TaskContext) -> dict:
        """Return the most recently mutated state, falling back to the initial load."""
        if "UpdateTaskStatusNode" in task_context.nodes:
            return task_context.get_node_output("UpdateTaskStatusNode")["result"]
        return task_context.get_node_output("LoadTaskStateNode")["result"]
