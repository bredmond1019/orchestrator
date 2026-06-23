"""EmbedQuestionNode — embed the user question at the start of the Q&A pipeline.

This node is the named first step in the ``DocumentQAWorkflow`` DAG. It embeds
the question text via ``EmbeddingService`` and stores both the question string
and its embedding vector so downstream nodes (``AssembleContextNode``) can
reference the question text without re-reading the event.

``RetrieveChunksNode`` re-embeds the question internally for its two-stage
retrieval call, which is intentional — the retrieval node is reused verbatim
across workflows and does not depend on this node's output. This node exists
to make the named DAG step explicit and to expose the embedding if a future
node needs it.
"""

from core.nodes.base import Node
from core.task import TaskContext
from services.embedding_service import EmbeddingService


class EmbedQuestionNode(Node):
    """Embed the question text and stash it in the task context."""

    def process(self, task_context: TaskContext) -> TaskContext:
        """Embed event.question and store the vector under this node's name."""
        question = task_context.event.question
        vector = EmbeddingService().embed_text(question)
        task_context.update_node(
            node_name=self.node_name,
            result={"question": question, "embedding": vector},
        )
        return task_context
