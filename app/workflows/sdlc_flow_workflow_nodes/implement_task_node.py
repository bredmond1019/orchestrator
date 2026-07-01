"""ImplementTaskNode — Claude Code coding agent for a single SDLC task.

LLM-driven node (extends ``AgentNode``). Reads the current task from
``TaskQueueRouterNode``'s output and the isolated worktree path from
``SetupWorktreeNode``'s output, then dispatches to Claude Code (via the
``CLAUDE_CODE_SDK`` provider seam) to author the code change for that task.
This node never writes code itself — it only builds the prompt, invokes the
agent, and records what the agent reports it did.

Output: ``result = {"summary": str, "modified_files": list[str],
"tests_added": list[str]}``.
"""

import json

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from services.prompt_loader import PromptManager


class ImplementTaskNode(AgentNode):
    """Agent node that drives Claude Code to implement one SDLC task."""

    class OutputType(AgentNode.OutputType):
        """Structured output: what Claude Code reports it implemented."""

        summary: str
        modified_files: list[str]
        tests_added: list[str]

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager.get_prompt(
                "sdlc_implement_task",
                task_title="",  # placeholder — real values are threaded via the user prompt
                task_description="",
                acceptance_criteria=[],
                breakdown_steps=[],
            ),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Implement the current task by dispatching to Claude Code.

        Reads:
          - ``TaskQueueRouterNode`` output (``current_task_id``, ``title``,
            ``description``, ``acceptance_criteria``)
          - ``SetupWorktreeNode`` output (``worktree_path``)

        Writes:
          - ``ImplementTaskNode`` result: ``summary``, ``modified_files``,
            ``tests_added``
        """
        current_task = task_context.get_node_output("TaskQueueRouterNode")["result"]
        worktree_path = task_context.get_node_output("SetupWorktreeNode")["result"][
            "worktree_path"
        ]

        task_title = current_task["title"]
        task_description = current_task["description"]
        acceptance_criteria = current_task.get("acceptance_criteria", [])
        breakdown_steps = current_task.get("breakdown_steps", [])

        # The system prompt built in get_agent_config() is a placeholder — the
        # real task fields are rendered here and swapped into the already
        # constructed Agent so a fresh Agent instance is not required per
        # task. ``Agent.system_prompt`` is a decorator method, not a plain
        # attribute, so the rendered prompt is written to the internal
        # ``_system_prompts`` tuple pydantic-ai actually reads at request
        # time.
        rendered_system_prompt = PromptManager.get_prompt(
            "sdlc_implement_task",
            task_title=task_title,
            task_description=task_description,
            acceptance_criteria=acceptance_criteria,
            breakdown_steps=breakdown_steps,
        )
        self.agent._system_prompts = (rendered_system_prompt,)  # pylint: disable=protected-access

        user_prompt = json.dumps(
            {
                "task_title": task_title,
                "task_description": task_description,
                "acceptance_criteria": acceptance_criteria,
                "worktree_path": worktree_path,
            },
            default=str,
        )

        result = self.run_agent_recorded(task_context, user_prompt)
        raw = result.output

        task_context.update_node(
            node_name=self.node_name,
            result={
                "summary": raw.summary,
                "modified_files": raw.modified_files,
                "tests_added": raw.tests_added,
            },
        )
        return task_context
