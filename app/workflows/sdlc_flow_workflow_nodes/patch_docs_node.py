"""PatchDocsNode — patches documentation references to changed symbols.

Agent node (extends ``AgentNode``, Sonnet-tier model via the ``ANTHROPIC``
provider). Reads the list of files ``ImplementTaskNode`` reports it modified,
builds a prompt asking the model to search ``docs/`` for stale references to
those files/symbols and patch them, and stores a summary plus the list of
files the model reports having patched.

This node does not touch the filesystem itself (no local docs-tree access
here) — the model performs any doc edits via its own tool use / the harness
that runs it; this node's job is to build the prompt and record what came
back.

Output: ``result = {"summary": str, "files_patched": list[str]}``.
"""

import json

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from services.prompt_loader import PromptManager


class PatchDocsNode(AgentNode):
    """Agent node that patches documentation for a task's modified files."""

    class OutputType(AgentNode.OutputType):
        """Structured summary of documentation changes made."""

        summary: str
        files_patched: list[str] = []

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager.get_prompt(
                "sdlc_patch_docs",
                modified_files=[],  # placeholder — real values threaded via the user prompt
            ),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.ANTHROPIC,
            model_name="claude-sonnet-5",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Patch documentation referencing the task's modified files.

        Reads:
          - ``ImplementTaskNode`` output (``modified_files``) — the most
            recent implementation pass's reported changes for this run.

        Writes:
          - ``PatchDocsNode`` result: ``summary``, ``files_patched``
        """
        modified_files = self._collect_modified_files(task_context)

        rendered_system_prompt = PromptManager.get_prompt(
            "sdlc_patch_docs",
            modified_files=modified_files,
        )
        self.agent._system_prompts = (rendered_system_prompt,)  # pylint: disable=protected-access

        user_prompt = json.dumps({"modified_files": modified_files}, default=str)

        result = self.run_agent_recorded(task_context, user_prompt)
        raw = result.output

        task_context.update_node(
            node_name=self.node_name,
            result={"summary": raw.summary, "files_patched": raw.files_patched},
        )
        return task_context

    @staticmethod
    def _collect_modified_files(task_context: TaskContext) -> list[str]:
        """Return the modified files reported by the most recent implementation pass.

        ``TaskContext.nodes`` stores one entry per node *name*, so across a
        retry loop only the latest ``ImplementTaskNode`` run is available
        here — this is that latest pass's reported ``modified_files``.
        """
        if "ImplementTaskNode" not in task_context.nodes:
            return []
        return task_context.get_node_output("ImplementTaskNode")["result"].get(
            "modified_files", []
        )
