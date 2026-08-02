"""RetrieveChunksNode — thin TaskContext adapter over ``app/brain/retrieval_engine.py``.

OR.K2 task 1 promoted the ~800-LOC two-stage hybrid retrieval pipeline this
node used to own (semantic -> structural -> keyword -> memory expansion,
score fusion, diversity cap) into ``app/brain/retrieval_engine.py`` so both
this node (the ``DOCUMENT_QA`` workflow) and ``app/brain/retrieval.py``
(``syn recall --hybrid`` / ``GET /recall?hybrid=true``) share one
implementation instead of the latter reaching into this node with an
inverted, function-local import. See ``retrieval_engine``'s module docstring
for the full pipeline description; this node now only reads event fields,
calls the engine, and writes the ``{"chunks", "retrieval_confidence"}``
result via ``update_node`` (CLAUDE.md standing rule 9).
"""

from brain import retrieval_engine
from core.nodes.base import Node
from core.task import TaskContext


class RetrieveChunksNode(Node):
    """Adapter: reads the event, delegates to ``retrieval_engine.retrieve``,
    stores the result. Build carefully — this node is reused verbatim by
    downstream workflows."""

    def process(self, task_context: TaskContext) -> TaskContext:
        """Run two-stage hybrid retrieval and store results in the task context."""
        event = task_context.event
        chunks = retrieval_engine.retrieve(
            event.question,
            corpus=getattr(event, "corpus", "content"),
            k=5,
            filters=getattr(event, "filters", None),
            include_archived=getattr(event, "include_archived", False),
            expand_structural=getattr(event, "expand_structural", True),
            workspace_id=getattr(event, "workspace_id", None),
            peer_id=getattr(event, "peer_id", None),
            include_memory=getattr(event, "include_memory", False),
            apply_decay=getattr(event, "apply_decay", True),
            surface="workflow",
        )
        task_context.update_node(
            node_name=self.node_name,
            result={
                "chunks": chunks,
                "retrieval_confidence": self._compute_retrieval_confidence(chunks),
            },
        )
        return task_context

    @staticmethod
    def _compute_retrieval_confidence(chunks: list[dict]) -> float:
        """Delegate to ``retrieval_engine.compute_retrieval_confidence``.

        Kept as a node-level staticmethod (rather than inlined at the call
        site) because it is a stable, independently-tested seam other
        workflow code (``GroundingRouterNode``, abstain-path tests) reaches
        via ``RetrieveChunksNode._compute_retrieval_confidence`` directly.
        """
        return retrieval_engine.compute_retrieval_confidence(chunks)
