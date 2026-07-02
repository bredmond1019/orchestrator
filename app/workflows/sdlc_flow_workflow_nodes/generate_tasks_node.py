"""GenerateTasksNode — authors a task spec for a spec directory that has none.

LLM-driven node (extends ``AgentNode``, Opus-tier model via the
``CLAUDE_CODE_SDK`` provider). This is the planning fallback: when a spec has
neither ``sdlc-flow-state.json`` nor ``tasks.json`` (see
``SpecExistsRouterNode``), this node reads whatever source material lives under
``planning/{spec_slug}/`` (plan, notes, synthesis, etc.), asks the model to
decompose it into an ordered, testable task list, and writes **both** the
human-facing ``tasks.md`` and the machine-facing ``tasks.json`` that
``LoadTaskStateNode`` consumes.

Output: ``result = {"tasks_json": str, "tasks_md": str, "task_count": int}``
(the paths written, plus how many tasks were generated).
"""

import json
from pathlib import Path

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import BaseModel, Field
from services.prompt_loader import PromptManager

# Filenames under planning/{spec_slug}/ that are NOT source material — the
# task list itself and the flow's own state.
_NON_CONTEXT_FILES = {"tasks.md", "tasks.json", "sdlc-flow-state.json"}


class GeneratedTask(BaseModel):
    """A single task authored by the planning model."""

    task_id: int = Field(..., description="1-indexed task number within the spec")
    title: str = Field(..., description="Short imperative task title")
    description: str = Field(..., description="Full task description / implementation notes")
    acceptance_criteria: list[str] = Field(
        default_factory=list, description="Observable acceptance criteria for this task"
    )


class GenerateTasksNode(AgentNode):
    """Agent node that authors a task spec (tasks.md + tasks.json) via Opus."""

    class OutputType(AgentNode.OutputType):
        """Structured task list plus the human-facing tasks.md document."""

        tasks: list[GeneratedTask] = []
        tasks_markdown: str = ""

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager.get_prompt(
                "sdlc_generate_tasks",
                spec_slug="",  # placeholder — real values threaded via the user prompt
                context="",
            ),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="opus",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Generate the task spec and write tasks.md + tasks.json to the worktree.

        Reads:
          - ``SetupWorktreeNode`` output (``worktree_path``)
          - the triggering event (``spec_slug``)
          - source material under ``planning/{spec_slug}/`` in the worktree

        Writes:
          - ``planning/{spec_slug}/tasks.md`` and ``tasks.json`` on disk
          - ``GenerateTasksNode`` result: ``tasks_json``, ``tasks_md``, ``task_count``
        """
        event = task_context.event
        spec_slug: str = event.spec_slug
        worktree_path = task_context.get_node_output("SetupWorktreeNode")["result"][
            "worktree_path"
        ]

        spec_dir = Path(worktree_path) / "planning" / spec_slug
        context = self._gather_context(spec_dir)

        rendered_system_prompt = PromptManager.get_prompt(
            "sdlc_generate_tasks",
            spec_slug=spec_slug,
            context=context,
        )
        self.agent._system_prompts = (rendered_system_prompt,)  # pylint: disable=protected-access

        user_prompt = json.dumps({"spec_slug": spec_slug, "context": context}, default=str)

        result = self.run_agent_recorded(task_context, user_prompt)
        raw = result.output

        spec_dir.mkdir(parents=True, exist_ok=True)
        tasks_json_path = spec_dir / "tasks.json"
        tasks_md_path = spec_dir / "tasks.md"

        tasks_payload = [task.model_dump() for task in raw.tasks]
        tasks_json_path.write_text(json.dumps(tasks_payload, indent=2), encoding="utf-8")
        tasks_md_path.write_text(raw.tasks_markdown, encoding="utf-8")

        task_context.update_node(
            node_name=self.node_name,
            result={
                "tasks_json": str(tasks_json_path),
                "tasks_md": str(tasks_md_path),
                "task_count": len(tasks_payload),
            },
        )
        return task_context

    @staticmethod
    def _gather_context(spec_dir: Path) -> str:
        """Concatenate the spec directory's source ``.md`` files as planning input."""
        if not spec_dir.exists():
            return ""
        parts: list[str] = []
        for path in sorted(spec_dir.glob("*.md")):
            if path.name in _NON_CONTEXT_FILES:
                continue
            parts.append(f"## {path.name}\n\n{path.read_text(encoding='utf-8')}")
        return "\n\n".join(parts)
