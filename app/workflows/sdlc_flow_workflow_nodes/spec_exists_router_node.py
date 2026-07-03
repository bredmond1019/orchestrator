"""SpecExistsRouterNode — routes on whether a task spec already exists.

Deterministic router (``BaseRouter`` / ``RouterNode`` pair, following the same
pattern as ``TaskQueueRouterNode``). Reads ``worktree_path`` from
``SetupWorktreeNode``'s output and ``spec_slug`` from the event, then:

- If ``planning/{spec_slug}/sdlc-flow-state.json`` OR
  ``planning/{spec_slug}/tasks.json`` exists → routes to ``LoadTaskStateNode``
  (the spec is ready to run / resume).
- Otherwise → routes to ``GenerateTasksNode`` (the planning fallback authors
  the spec first, then hands off to ``LoadTaskStateNode``).

This keeps the (Opus) planning step out of the common path: it only fires when
a spec genuinely has no task list.
"""

from core.nodes.base import Node
from core.nodes.router import BaseRouter, RouterNode
from core.task import TaskContext

from workflows.sdlc_flow_workflow_nodes._shared import get_spec_dir


class SpecExistsRouterNode(BaseRouter):
    """Router that branches on whether the spec already has a task list."""

    def __init__(self):
        self.routes = [_SpecExistsRouter()]
        self.fallback = None


class _SpecExistsRouter(RouterNode):
    """Routes to LoadTaskStateNode when a spec exists, else GenerateTasksNode."""

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        # Local imports avoid an import cycle between the SDLC flow nodes.
        from workflows.sdlc_flow_workflow_nodes.generate_tasks_node import (  # pylint: disable=import-outside-toplevel,cyclic-import
            GenerateTasksNode,
        )
        from workflows.sdlc_flow_workflow_nodes.load_task_state_node import (  # pylint: disable=import-outside-toplevel,cyclic-import
            LoadTaskStateNode,
        )

        event = task_context.event
        spec_slug: str = event.spec_slug
        spec_dir = get_spec_dir(task_context, spec_slug)
        state_path = spec_dir / "sdlc-flow-state.json"
        tasks_path = spec_dir / "tasks.json"

        if state_path.exists() or tasks_path.exists():
            return LoadTaskStateNode()
        return GenerateTasksNode()
