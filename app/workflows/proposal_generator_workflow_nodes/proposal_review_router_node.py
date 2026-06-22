"""ProposalReviewRouterNode — routes on review verdict from ProposalReviewNode.

Routes ``pass`` verdict to ``StorageNode`` and ``revise`` verdict to
``ReviseNode``. The DAG is acyclic: ``ReviseNode`` connects to ``StorageNode``
but never loops back to review. Implements ``BaseRouter`` + ``RouterNode``
following the ``BlogDecisionRouterNode`` pattern.
"""

from core.nodes.base import Node
from core.nodes.router import BaseRouter, RouterNode
from core.task import TaskContext

from workflows.proposal_generator_workflow_nodes.proposal_revise_node import (
    ProposalReviseNode,
)
from workflows.proposal_generator_workflow_nodes.storage_node import StorageNode


class ProposalReviewRouterNode(BaseRouter):
    """Router that branches on the ProposalReviewNode verdict.

    ``pass``   → StorageNode
    ``revise`` → ProposalReviseNode
    """

    def __init__(self):
        self.routes = [_ReviewVerdictRouter()]
        self.fallback = None


class _ReviewVerdictRouter(RouterNode):
    """Evaluates the review verdict and returns the correct next node."""

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        review = task_context.get_node_output("ProposalReviewNode")
        result = review.get("result")
        if result is None:
            return None

        # verdict may be a Pydantic model or a plain dict (after serialization).
        verdict = (
            result.verdict
            if hasattr(result, "verdict")
            else result.get("verdict", "revise")
        )

        if verdict == "pass":
            return StorageNode()
        return ProposalReviseNode()
