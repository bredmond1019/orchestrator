"""GroundingRouterNode — abstain-gate router for the Document Q&A workflow.

Sits after ``RetrieveChunksNode`` and decides whether the retrieved context is
strong enough to attempt an answer at all (block OR.L, design decision 2).

Routes to ``AbstainNode`` (deterministic, no LLM call) when the retrieval
confidence signal computed by ``RetrieveChunksNode`` falls below the event's
``confidence_threshold`` — or when zero chunks were retrieved at all — and
otherwise falls through to the normal ``AssembleContextNode`` -> ``AnswerNode``
path. Mirrors the ``BlogDecisionRouterNode`` shape (a single ``RouterNode``
plus fallback).

Reads the upstream ``RetrieveChunksNode`` output via
``TaskContext.get_node_output()`` so a mis-ordered workflow (this router
running before retrieval) surfaces the framework's descriptive ``KeyError``
instead of a raw one.
"""

from core.nodes.base import Node
from core.nodes.router import BaseRouter, RouterNode
from core.task import TaskContext

from workflows.document_qa_workflow_nodes.abstain_node import AbstainNode
from workflows.document_qa_workflow_nodes.assemble_context_node import (
    AssembleContextNode,
)


class GroundingRouterNode(BaseRouter):
    """Router that gates the answer path on retrieval confidence."""

    def __init__(self):
        self.routes = [BelowConfidenceRouter()]
        # Fallback: confident retrieval proceeds to the normal answer path.
        self.fallback = AssembleContextNode()


class BelowConfidenceRouter(RouterNode):
    """Routes to the deterministic abstain path when retrieval is too weak."""

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        retrieve_result = task_context.get_node_output("RetrieveChunksNode")["result"]
        chunks: list[dict] = retrieve_result.get("chunks", [])
        confidence: float = retrieve_result.get("retrieval_confidence", 0.0)
        threshold: float = task_context.event.confidence_threshold

        if not chunks or confidence < threshold:
            return AbstainNode()
        return None
