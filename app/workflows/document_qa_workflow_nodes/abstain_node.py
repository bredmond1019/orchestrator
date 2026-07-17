"""AbstainNode — deterministic below-confidence abstain path (block OR.L).

Runs in place of ``AssembleContextNode -> AnswerNode`` when
``GroundingRouterNode`` decides the retrieved context is too weak (or empty)
to attempt a grounded answer. Makes no LLM call — the answer envelope is
written directly, matching the block's "abstain is a routed branch, not a
prompt rule" design decision.

Writes the unified answer envelope (design decision 5) so
``UpdateSessionMemoryNode`` can persist the turn identically regardless of
which branch produced it.
"""

from core.nodes.base import Node
from core.task import TaskContext

ABSTAIN_MESSAGE = "I don't have that in my documents."


class AbstainNode(Node):
    """Deterministic node that writes the abstain answer envelope."""

    def process(self, task_context: TaskContext) -> TaskContext:
        """Write the abstain envelope from the retrieval confidence signal.

        Reads:
          - ``RetrieveChunksNode`` output: ``retrieval_confidence``.

        Writes:
          - ``AbstainNode`` result: the unified answer envelope with
            ``abstained: true``.
        """
        retrieve_result = task_context.get_node_output("RetrieveChunksNode")["result"]
        context_confidence: float = retrieve_result.get("retrieval_confidence", 0.0)

        task_context.update_node(
            node_name=self.node_name,
            result={
                "answer": ABSTAIN_MESSAGE,
                "cited_sections": [],
                "verified_citations": [],
                "unverified_citations": [],
                "context_confidence": context_confidence,
                "abstained": True,
                "corroborated": False,
                "escalate_to_human": True,
                "withheld_reason": "below_confidence_threshold",
            },
        )
        return task_context
