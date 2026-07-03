"""Shared helpers for sdlc-flow nodes.

Small utilities reused across multiple nodes in this package. Keep this
module free of node-specific logic — it exists only to avoid duplicating
the ``SetupWorktreeNode`` output lookup pattern.
"""

from pathlib import Path

from core.task import TaskContext


def get_spec_dir(task_context: TaskContext, spec_slug: str) -> Path:
    """Resolve ``planning/{spec_slug}`` under the worktree set up by ``SetupWorktreeNode``."""
    worktree_path = task_context.get_node_output("SetupWorktreeNode")["result"]["worktree_path"]
    return Path(worktree_path) / "planning" / spec_slug
