"""PullRequestNode — pushes the worktree branch and opens a PR for human review.

Deterministic node (no LLM). Reads ``worktree_path`` / ``branch_name`` from
``SetupWorktreeNode``'s output and ``auto_pr`` / ``spec_slug`` from the
triggering event. If ``auto_pr`` is false, this node is a no-op — it stores
``{"pr_url": None, "skipped": True}`` and returns without touching git or
``gh``. Otherwise it pushes the branch to ``origin`` and runs
``gh pr create`` via subprocess, storing the resulting PR URL.

This node deliberately does **not** auto-merge (human review gate, D25) —
merging the PR is a separate, human-triggered action.

Output: ``result = {"pr_url": str | None, "skipped": bool}``.
"""

import logging
import subprocess

from core.nodes.base import Node
from core.task import TaskContext

logger = logging.getLogger(__name__)


class PullRequestNode(Node):
    """Push the task's branch and open a PR (no auto-merge)."""

    def process(self, task_context: TaskContext) -> TaskContext:
        event = task_context.event
        auto_pr = getattr(event, "auto_pr", True)

        if not auto_pr:
            logger.info("PullRequestNode: auto_pr is False, skipping PR creation")
            task_context.update_node(
                node_name=self.node_name, result={"pr_url": None, "skipped": True}
            )
            return task_context

        setup_output = task_context.get_node_output("SetupWorktreeNode")["result"]
        worktree_path = setup_output["worktree_path"]
        branch_name = setup_output["branch_name"]
        spec_slug = event.spec_slug

        push_result = subprocess.run(
            ["git", "push", "origin", branch_name],
            capture_output=True,
            text=True,
            check=False,
            cwd=worktree_path,
        )
        if push_result.returncode != 0:
            raise RuntimeError(f"git push failed: {push_result.stderr}")

        pr_result = subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                branch_name,
                "--title",
                f"SDLC: {spec_slug}",
                "--body",
                "Auto-generated PR — human review required.",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=worktree_path,
        )
        if pr_result.returncode != 0:
            raise RuntimeError(f"gh pr create failed: {pr_result.stderr}")

        pr_url = pr_result.stdout.strip()

        task_context.update_node(
            node_name=self.node_name, result={"pr_url": pr_url, "skipped": False}
        )
        return task_context
