"""AnswerNode — grounded Q&A answer generation for the Document Q&A workflow.

An ``AgentNode`` subclass that produces a structured answer grounded strictly
in the assembled RAG context and prior session memory provided by
``AssembleContextNode``.

The system prompt is loaded from ``app/prompts/document_qa_answer.j2`` via
``PromptManager`` — no system prompt is hardcoded here (CLAUDE.md rule 2).

``run_agent_recorded`` is used (not ``self.agent.run_sync``) so per-node
telemetry (input tokens, output tokens, model) is captured by the framework
and surfaced in the data contract read by Bastion (D30).
"""

import json

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.task import TaskContext
from pydantic import Field
from services.prompt_loader import PromptManager


class AnswerNode(AgentNode):
    """Agent node that generates a grounded answer from the RAG context."""

    class OutputType(AgentNode.OutputType):
        """Structured output: the answer text and any cited section titles."""

        answer: str = Field(description="The grounded answer to the user question")
        cited_sections: list[str] = Field(
            default_factory=list,
            description="Section titles cited in the answer",
        )

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager().get_prompt("document_qa_answer"),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Generate the grounded answer from assembled context.

        Reads:
          - ``AssembleContextNode`` output: ``context``, ``history``, ``question``.

        Writes:
          - ``AnswerNode`` result: serialized ``OutputType``
            (``answer``, ``cited_sections``).
        """
        assembled = task_context.get_node_output("AssembleContextNode")["result"]
        context_block: str = assembled.get("context", "")
        history: list[dict] = assembled.get("history", [])
        question: str = assembled.get("question", "")

        # Build the user prompt: history transcript + RAG context + question
        user_prompt = json.dumps(
            {
                "prior_conversation": history,
                "document_context": context_block,
                "question": question,
            },
            ensure_ascii=False,
        )

        result = self.run_agent_recorded(task_context, user_prompt)
        task_context.update_node(node_name=self.node_name, result=result.output)
        return task_context
