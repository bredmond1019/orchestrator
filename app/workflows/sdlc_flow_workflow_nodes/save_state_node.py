"""SaveStateNode — persists the current SDLC flow state to disk and commits it.

Deterministic node (no LLM). Reads the most recently mutated ``SDLCState``
from ``TaskContext`` (``UpdateTaskStatusNode`` output when present, otherwise
the initial ``LoadTaskStateNode`` output), writes it to
``planning/{spec_slug}/sdlc-flow-state.json`` inside the worktree, and commits
the file via ``git add`` + ``git commit`` so state survives across resumed
runs.

Output: ``result = {"saved_to": str}``.
"""

import logging
import subprocess
from pathlib import Path

from core.nodes.base import Node
from core.task import TaskContext
from schemas.sdlc_schema import SDLCState

logger = logging.getLogger(__name__)


class SaveStateNode(Node):
    """Serialize the current SDLC flow state and commit it in the worktree."""

    def process(self, task_context: TaskContext) -> TaskContext:
        worktree_path = task_context.get_node_output("SetupWorktreeNode")["result"][
            "worktree_path"
        ]

        if "UpdateTaskStatusNode" in task_context.nodes:
            state_dict = task_context.get_node_output("UpdateTaskStatusNode")["result"]
        else:
            state_dict = task_context.get_node_output("LoadTaskStateNode")["result"]

        state = SDLCState.model_validate(state_dict)

        state_path = Path(worktree_path) / "planning" / state.spec_slug / "sdlc-flow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

        subprocess.run(
            ["git", "add", str(state_path)],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        result = subprocess.run(
            ["git", "commit", "-m", "chore: flow state update"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.info("git commit produced no changes or failed: %s", result.stderr)

        task_context.update_node(node_name=self.node_name, result={"saved_to": str(state_path)})
        return task_context
