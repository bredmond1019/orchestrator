"""SetupWorktreeNode — creates (or reattaches to) an isolated git worktree.

Deterministic node (no LLM). Given the ``SDLCFlowEventSchema`` on the
``TaskContext`` event, this node computes the branch name and worktree path,
creates the worktree via ``git worktree add`` (or reattaches when
``resume=True`` and the worktree already exists), copies over an ``.env``
template if present, and stores ``worktree_path`` / ``branch_name`` for
downstream nodes.

Output: ``result = {"worktree_path": str, "branch_name": str}``.
"""

import logging
import shutil
import subprocess
from pathlib import Path

from core.nodes.base import Node
from core.task import TaskContext

logger = logging.getLogger(__name__)


class SetupWorktreeNode(Node):
    """Create or reattach to an isolated git worktree for SDLC execution."""

    def process(self, task_context: TaskContext) -> TaskContext:
        event = task_context.event
        spec_slug: str = event.spec_slug
        resume: bool = event.resume
        branch_name: str | None = getattr(event, "branch_name", None)

        branch = branch_name or f"sdlc/{spec_slug}"
        worktree_path = Path("trees") / branch

        if resume and worktree_path.exists():
            logger.info("Reattaching to existing worktree: %s", worktree_path)
        else:
            result = subprocess.run(
                ["git", "worktree", "add", str(worktree_path), "-b", branch, "origin/main"],
                capture_output=True,
                text=True,
                check=False,
                cwd=".",
            )
            if result.returncode != 0:
                logger.info("git worktree add failed, attempting cleanup: %s", result.stderr)
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=".",
                )
                raise RuntimeError(f"git worktree add failed: {result.stderr}")

        env_template = Path("app/.env")
        worktree_env = worktree_path / "app" / ".env"
        if env_template.exists() and not worktree_env.exists():
            worktree_env.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(env_template, worktree_env)

        task_context.update_node(
            node_name=self.node_name,
            result={"worktree_path": str(worktree_path), "branch_name": branch},
        )
        return task_context
