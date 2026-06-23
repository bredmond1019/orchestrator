"""EmbedChunksNode — embed all chunk texts in a single batched Voyage call.

Reads the chunk list produced by ``ChunkDocumentNode``, passes all chunk
``content`` strings to ``EmbeddingService.embed_batch`` in one call, and zips
the returned vectors back onto each chunk dict under the key ``"embedding"``.

Constructing ``EmbeddingService`` inside ``process`` (rather than at
import time or in ``__init__``) allows tests to patch
``workflows.document_ingest_workflow_nodes.embed_chunks_node.EmbeddingService``
without needing a real Voyage API key.

Output: ``result = {"chunks": [<chunk_dict_with_embedding>, ...]}``.
"""

from core.nodes.base import Node
from core.task import TaskContext
from services.embedding_service import EmbeddingService


class EmbedChunksNode(Node):
    """Embed all document chunks in a single batched API call."""

    def process(self, task_context: TaskContext) -> TaskContext:
        chunk_result = task_context.get_node_output("ChunkDocumentNode")["result"]
        chunks: list[dict] = chunk_result["chunks"]

        texts = [c["content"] for c in chunks]
        vectors = EmbeddingService().embed_batch(texts)

        chunks_with_embeddings = [
            {**chunk, "embedding": vector}
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]

        task_context.update_node(
            node_name=self.node_name,
            result={"chunks": chunks_with_embeddings},
        )
        return task_context
