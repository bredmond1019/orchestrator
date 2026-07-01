"""LoadTaskStateNode — reads (or bootstraps) the structured SDLC flow state.

Deterministic node (no LLM). Reads ``spec_slug`` / ``task_range`` from the
``SDLCFlowEventSchema`` event and ``worktree_path`` from
``SetupWorktreeNode``'s output, then loads
``planning/{spec_slug}/sdlc-flow-state.json`` if it already exists (a resumed
or in-progress run), or bootstraps an initial ``SDLCState`` from
``planning/{spec_slug}/tasks.json`` otherwise. Applies the optional
``task_range`` filter before storing the state for downstream nodes.

Output: ``result = SDLCState.model_dump()`` (filtered by ``task_range``).
"""

import json
import logging
from pathlib import Path

from core.nodes.base import Node
from core.task import TaskContext
from schemas.sdlc_schema import SDLCFlowEventSchema, SDLCState

logger = logging.getLogger(__name__)


class LoadTaskStateNode(Node):
    """Load or bootstrap the durable SDLC flow state for a spec run."""

    def process(self, task_context: TaskContext) -> TaskContext:
        event: SDLCFlowEventSchema = task_context.event
        spec_slug: str = event.spec_slug
        task_range: str | None = event.task_range

        worktree_path = task_context.get_node_output("SetupWorktreeNode")["result"][
            "worktree_path"
        ]

        state_path = Path(worktree_path) / "planning" / spec_slug / "sdlc-flow-state.json"
        tasks_path = Path(worktree_path) / "planning" / spec_slug / "tasks.json"

        if state_path.exists():
            logger.info("Loading existing SDLC flow state from %s", state_path)
            state = SDLCState.model_validate_json(state_path.read_text(encoding="utf-8"))
        elif tasks_path.exists():
            logger.info("Bootstrapping SDLC flow state from %s", tasks_path)
            tasks_data = json.loads(tasks_path.read_text(encoding="utf-8"))
            state = SDLCState(spec_slug=spec_slug, tasks=tasks_data)
        else:
            raise FileNotFoundError(f"No state or tasks file found for {spec_slug}")

        task_ids = SDLCFlowEventSchema.parse_task_range(task_range)
        if task_ids is not None:
            state.tasks = [task for task in state.tasks if task.task_id in task_ids]

        task_context.update_node(node_name=self.node_name, result=state.model_dump())
        return task_context
