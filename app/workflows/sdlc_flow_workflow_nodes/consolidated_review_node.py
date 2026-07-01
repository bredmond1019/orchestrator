"""ConsolidatedReviewNode — reviews the full task diff against acceptance criteria.

Agent node (extends ``AgentNode``, Sonnet-tier model via the ``ANTHROPIC``
provider). Reads the full ``git diff main..HEAD`` from the task's isolated
worktree, builds a prompt from that diff plus the current task's
``acceptance_criteria``, and asks the model to issue an ``SDLCReviewVerdict``
(``PASS`` / ``FAIL`` / ``PARTIAL``) with a summary and a list of issues.

Paired with ``ReviewRouterNode`` (in ``review_router_node.py``), which routes
on the stored verdict:
    ``PASS``                       -> ``UpdateTaskStatusNode``
    ``FAIL`` / ``PARTIAL`` (minor)  -> ``ImplementTaskNode`` (re-implement)
    ``FAIL`` (structural)          -> ``WrapUpNode``

Output: ``result = {"verdict": str, "summary": str, "issues": list[str]}``.
"""

# The AgentConfig boilerplate + run_agent_recorded call every AgentNode
# subclass repeats trips R0801 against sibling nodes; it is the prescribed
# framework pattern, not a refactor target.
# pylint: disable=duplicate-code

import json
import subprocess

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from services.prompt_loader import PromptManager


class ConsolidatedReviewNode(AgentNode):
    """Agent node that reviews a task's git diff against its acceptance criteria."""

    class OutputType(AgentNode.OutputType):
        """Structured verdict emitted by the review model."""

        verdict: str
        summary: str
        issues: list[str] = []

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager.get_prompt(
                "sdlc_review",
                acceptance_criteria=[],  # placeholder — real values threaded via the user prompt
                git_diff="",
            ),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.ANTHROPIC,
            model_name="claude-sonnet-5",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Review the current task's diff against its acceptance criteria.

        Reads:
          - ``SetupWorktreeNode`` output (``worktree_path``)
          - ``TaskQueueRouterNode`` output (``acceptance_criteria``)

        Writes:
          - ``ConsolidatedReviewNode`` result: ``verdict``, ``summary``, ``issues``
        """
        worktree_path = task_context.get_node_output("SetupWorktreeNode")["result"][
            "worktree_path"
        ]
        current_task = task_context.get_node_output("TaskQueueRouterNode")["result"]
        acceptance_criteria = current_task.get("acceptance_criteria", [])

        diff_result = subprocess.run(
            ["git", "diff", "main..HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=worktree_path,
        )
        git_diff = diff_result.stdout

        rendered_system_prompt = PromptManager.get_prompt(
            "sdlc_review",
            acceptance_criteria=acceptance_criteria,
            git_diff=git_diff,
        )
        self.agent._system_prompts = (rendered_system_prompt,)  # pylint: disable=protected-access

        user_prompt = json.dumps(
            {"acceptance_criteria": acceptance_criteria, "git_diff": git_diff},
            default=str,
        )

        result = self.run_agent_recorded(task_context, user_prompt)
        raw = result.output

        task_context.update_node(
            node_name=self.node_name,
            result={"verdict": raw.verdict, "summary": raw.summary, "issues": raw.issues},
        )
        return task_context
