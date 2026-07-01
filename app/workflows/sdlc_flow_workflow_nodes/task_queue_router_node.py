"""TaskQueueRouterNode — iterates the SDLC task queue.

Deterministic router (``BaseRouter`` / ``RouterNode`` pair, following the same
pattern as ``TriageRouterNode`` / ``ReviewRouterNode``). Reads the most
recently mutated ``SDLCState`` (``UpdateTaskStatusNode`` output if this is not
the first pass through the loop, otherwise ``LoadTaskStateNode``'s initial
load), finds the first task whose ``status`` is still ``PENDING``, and:

- If a pending task is found: stores that task's fields on
  ``TaskQueueRouterNode``'s own output (so downstream nodes —
  ``ImplementTaskNode``, ``TriageTaskNode``, ``ConsolidatedReviewNode``,
  ``UpdateTaskStatusNode`` — can read ``current_task_id`` / ``title`` /
  ``description`` / ``acceptance_criteria`` / ``attempt_count`` /
  ``max_attempts`` without re-parsing ``SDLCState`` themselves) and routes to
  ``ImplementTaskNode``.
- If no ``PENDING`` task remains: routes to ``PatchDocsNode`` (the task loop
  is over; the run moves to the completion phase).

This node is the sole place the cyclic "next task" loop-back is expressed:
the back-edge to ``ImplementTaskNode`` is a *runtime* routing decision (via
``determine_next_node``), not a declared ``NodeConfig.connections`` edge —
see ``SDLCFlowWorkflow`` and the ``WorkflowValidator._has_cycle`` router
exemption in ``core/validate.py`` for why this does not trip cycle detection.

Output: ``result = {"current_task_id": int, "title": str, "description": str,
"acceptance_criteria": list[str], "attempt_count": int, "max_attempts": int}``
when a task is dispatched; omitted (no result written) when the loop ends and
control routes straight to ``PatchDocsNode``.
"""

from core.nodes.base import Node
from core.nodes.router import BaseRouter, RouterNode
from core.task import TaskContext
from schemas.sdlc_schema import SDLCState, SDLCTaskStatus


class TaskQueueRouterNode(BaseRouter):
    """Router that dispatches the next PENDING task or ends the task loop."""

    def __init__(self):
        self.routes = [_TaskQueueRouter()]
        self.fallback = None


class _TaskQueueRouter(RouterNode):
    """Finds the next PENDING task (if any) and routes accordingly."""

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        # Local imports avoid an import cycle between the SDLC flow nodes.
        from workflows.sdlc_flow_workflow_nodes.implement_task_node import (  # pylint: disable=import-outside-toplevel,cyclic-import
            ImplementTaskNode,
        )
        from workflows.sdlc_flow_workflow_nodes.patch_docs_node import (  # pylint: disable=import-outside-toplevel,cyclic-import
            PatchDocsNode,
        )

        state = SDLCState.model_validate(self._latest_state_dict(task_context))

        next_task = next(
            (task for task in state.tasks if task.status == SDLCTaskStatus.PENDING),
            None,
        )

        if next_task is None:
            return PatchDocsNode()

        task_context.update_node(
            node_name="TaskQueueRouterNode",
            result={
                "current_task_id": next_task.task_id,
                "title": next_task.title,
                "description": next_task.description,
                "acceptance_criteria": next_task.acceptance_criteria,
                "attempt_count": next_task.attempt_count,
                "max_attempts": next_task.max_attempts,
            },
        )
        return ImplementTaskNode()

    @staticmethod
    def _latest_state_dict(task_context: TaskContext) -> dict:
        """Return the most recently mutated state, falling back to the initial load."""
        if "UpdateTaskStatusNode" in task_context.nodes:
            return task_context.get_node_output("UpdateTaskStatusNode")["result"]
        return task_context.get_node_output("LoadTaskStateNode")["result"]
