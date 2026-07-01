"""ReviewRouterNode — routes on the ``ConsolidatedReviewNode`` verdict.

Deterministic router (``BaseRouter`` / ``RouterNode`` pair, following the same
pattern as ``TriageRouterNode`` in ``triage_task_node.py``):

    ``PASS``                        -> ``UpdateTaskStatusNode``
    ``FAIL`` / ``PARTIAL`` (minor)   -> ``ImplementTaskNode`` (re-implement)
    ``FAIL`` (structural)           -> ``WrapUpNode``

"Structural" vs. "minor" is distinguished by issue count: a small number of
issues is treated as fixable by another implementation pass; a large number
(or an empty issue list on a non-PASS verdict, signalling the model judged
the diff fundamentally off-track) is treated as structural and routed to
``WrapUpNode`` instead of burning further attempts.
"""

from core.nodes.base import Node
from core.nodes.router import BaseRouter, RouterNode
from core.task import TaskContext
from schemas.sdlc_schema import SDLCReviewVerdict

# A review with more than this many distinct issues is treated as a
# structural failure (re-implementation is unlikely to converge) rather than
# a minor, fixable one.
_STRUCTURAL_ISSUE_THRESHOLD = 5


class ReviewRouterNode(BaseRouter):
    """Router that branches on the ``ConsolidatedReviewNode`` verdict."""

    def __init__(self):
        self.routes = [_ReviewVerdictRouter()]
        self.fallback = None


class _ReviewVerdictRouter(RouterNode):
    """Evaluates the review verdict and returns the correct next node."""

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        # Local imports avoid an import cycle between the SDLC flow nodes.
        from workflows.sdlc_flow_workflow_nodes.implement_task_node import (  # pylint: disable=import-outside-toplevel,cyclic-import
            ImplementTaskNode,
        )
        from workflows.sdlc_flow_workflow_nodes.update_task_status_node import (  # pylint: disable=import-outside-toplevel,cyclic-import
            UpdateTaskStatusNode,
        )
        from workflows.sdlc_flow_workflow_nodes.wrap_up_node import (  # pylint: disable=import-outside-toplevel,cyclic-import
            WrapUpNode,
        )

        review = task_context.get_node_output("ConsolidatedReviewNode")
        result = review.get("result") if isinstance(review, dict) else None
        if result is None:
            return None

        verdict = result.verdict if hasattr(result, "verdict") else result.get("verdict")
        issues = result.issues if hasattr(result, "issues") else result.get("issues", [])

        if verdict == SDLCReviewVerdict.PASS.value:
            return UpdateTaskStatusNode()
        if verdict in (SDLCReviewVerdict.FAIL.value, SDLCReviewVerdict.PARTIAL.value):
            if len(issues or []) > _STRUCTURAL_ISSUE_THRESHOLD:
                return WrapUpNode()
            return ImplementTaskNode()
        return None
