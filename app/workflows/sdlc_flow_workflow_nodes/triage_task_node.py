"""TriageTaskNode — classifies a task's test failure and routes accordingly.

Split into two nodes following the ``ProposalReviewNode`` /
``ProposalReviewRouterNode`` pattern already used in this codebase (the
``BaseRouter``/``RouterNode`` pair is deterministic routing, not an LLM call):

- ``TriageTaskNode`` (``AgentNode``): uses a mid-tier model (Sonnet, via the
  ``CLAUDE_CODE_SDK`` provider) to classify the ``TestTaskNode`` failure output
  into ``PASS`` / ``RETRYABLE`` / ``MAJOR_BAIL`` with a one-line reason. Before
  invoking the model, ``max_attempts`` is enforced deterministically: if the
  current task has already reached its attempt budget, the verdict is forced
  to ``MAJOR_BAIL`` without a model call.
- ``TriageRouterNode`` (``BaseRouter``): reads ``TriageTaskNode``'s stored
  verdict and routes:
    ``PASS``        → ``ConsolidatedReviewNode``
    ``RETRYABLE``   → ``ImplementTaskNode`` (retry)
    ``MAJOR_BAIL``  → ``WrapUpNode``

Output of ``TriageTaskNode``: ``result = {"verdict": str, "reason": str}``
(``verdict`` is one of the ``SDLCTriageVerdict`` values).
"""

# The AgentConfig boilerplate + run_agent_recorded call every AgentNode
# subclass repeats trips R0801 against sibling nodes; it is the prescribed
# framework pattern, not a refactor target.
# pylint: disable=duplicate-code

import json

from core.nodes.agent import AgentConfig, AgentNode, ModelProvider
from core.nodes.base import Node
from core.nodes.router import BaseRouter, RouterNode
from core.task import TaskContext
from schemas.sdlc_schema import SDLCTriageVerdict
from services.prompt_loader import PromptManager


class TriageTaskNode(AgentNode):
    """Agent node that classifies a task's test-failure output."""

    class OutputType(AgentNode.OutputType):
        """Structured verdict emitted by the triage model."""

        verdict: str
        reason: str

    def get_agent_config(self) -> AgentConfig:
        return AgentConfig(
            system_prompt=PromptManager.get_prompt(
                "sdlc_triage",
                failure_summary="",  # placeholder — real values threaded via the user prompt
                task_title="",
                attempt_count=0,
                max_attempts=3,
            ),
            output_type=self.OutputType,
            deps_type=None,
            model_provider=ModelProvider.CLAUDE_CODE_SDK,
            model_name="sonnet",
        )

    def process(self, task_context: TaskContext) -> TaskContext:
        """Classify the current task's test result and store the verdict.

        Reads:
          - ``TestTaskNode`` output (``all_passed``, ``failure_summary``)
          - ``TaskQueueRouterNode`` output (``current_task_id``, ``title``,
            ``attempt_count``, ``max_attempts``)

        Writes:
          - ``TriageTaskNode`` result: ``verdict``, ``reason``
        """
        test_result = task_context.get_node_output("TestTaskNode")["result"]
        current_task = task_context.get_node_output("TaskQueueRouterNode")["result"]

        task_title = current_task.get("title", "")
        attempt_count = current_task.get("attempt_count", 0)
        max_attempts = current_task.get("max_attempts", 3)

        if test_result.get("all_passed"):
            task_context.update_node(
                node_name=self.node_name,
                result={
                    "verdict": SDLCTriageVerdict.PASS.value,
                    "reason": "All harness checks passed.",
                },
            )
            return task_context

        if attempt_count >= max_attempts:
            task_context.update_node(
                node_name=self.node_name,
                result={
                    "verdict": SDLCTriageVerdict.MAJOR_BAIL.value,
                    "reason": f"Max attempts ({max_attempts}) reached without a passing run.",
                },
            )
            return task_context

        failure_summary = test_result.get("failure_summary", "")

        rendered_system_prompt = PromptManager.get_prompt(
            "sdlc_triage",
            failure_summary=failure_summary,
            task_title=task_title,
            attempt_count=attempt_count,
            max_attempts=max_attempts,
        )
        self.agent._system_prompts = (rendered_system_prompt,)  # pylint: disable=protected-access

        user_prompt = json.dumps(
            {
                "failure_summary": failure_summary,
                "task_title": task_title,
                "attempt_count": attempt_count,
                "max_attempts": max_attempts,
            },
            default=str,
        )

        result = self.run_agent_recorded(task_context, user_prompt)
        raw = result.output

        task_context.update_node(
            node_name=self.node_name,
            result={"verdict": raw.verdict, "reason": raw.reason},
        )
        return task_context


class TriageRouterNode(BaseRouter):
    """Router that branches on the ``TriageTaskNode`` verdict.

    ``PASS``        → ConsolidatedReviewNode
    ``RETRYABLE``   → ImplementTaskNode
    ``MAJOR_BAIL``  → WrapUpNode
    """

    def __init__(self):
        self.routes = [_TriageVerdictRouter()]
        self.fallback = None


class _TriageVerdictRouter(RouterNode):
    """Evaluates the triage verdict and returns the correct next node."""

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        # Local imports avoid an import cycle between the SDLC flow nodes.
        from workflows.sdlc_flow_workflow_nodes.consolidated_review_node import (  # pylint: disable=import-outside-toplevel,cyclic-import
            ConsolidatedReviewNode,
        )
        from workflows.sdlc_flow_workflow_nodes.implement_task_node import (  # pylint: disable=import-outside-toplevel,cyclic-import
            ImplementTaskNode,
        )
        from workflows.sdlc_flow_workflow_nodes.wrap_up_node import (  # pylint: disable=import-outside-toplevel,cyclic-import
            WrapUpNode,
        )

        triage = task_context.get_node_output("TriageTaskNode")
        result = triage.get("result") if isinstance(triage, dict) else None
        if result is None:
            return None

        verdict = result.verdict if hasattr(result, "verdict") else result.get("verdict")

        if verdict == SDLCTriageVerdict.PASS.value:
            return ConsolidatedReviewNode()
        if verdict == SDLCTriageVerdict.RETRYABLE.value:
            return ImplementTaskNode()
        if verdict == SDLCTriageVerdict.MAJOR_BAIL.value:
            return WrapUpNode()
        return None
