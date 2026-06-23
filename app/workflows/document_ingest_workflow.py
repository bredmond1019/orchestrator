"""DocumentIngestWorkflow — ingest a document into embedded ContentChunk rows (Project D).

Parses the source document, splits it into section-aware overlapping token
chunks, embeds all chunks in a single batched Voyage call, and persists every
``ContentChunk`` row (with embedding) via ``GenericRepository``.

Graph (linear DAG — no router)::

    ParseDocumentNode
        -> ChunkDocumentNode
            -> EmbedChunksNode
                -> StoreChunksNode
"""

from core.schema import NodeConfig, WorkflowSchema
from core.workflow import Workflow
from schemas.document_ingest_schema import DocumentIngestEventSchema

from workflows.document_ingest_workflow_nodes.chunk_document_node import (
    ChunkDocumentNode,
)
from workflows.document_ingest_workflow_nodes.embed_chunks_node import EmbedChunksNode
from workflows.document_ingest_workflow_nodes.parse_document_node import (
    ParseDocumentNode,
)
from workflows.document_ingest_workflow_nodes.store_chunks_node import StoreChunksNode


class DocumentIngestWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description=(
            "Document ingestion pipeline: parse raw text or PDF -> section-aware "
            "chunking -> batched Voyage embedding -> persist ContentChunk rows."
        ),
        event_schema=DocumentIngestEventSchema,
        start=ParseDocumentNode,
        nodes=[
            NodeConfig(
                node=ParseDocumentNode,
                connections=[ChunkDocumentNode],
                description="Normalise the ingest event into plain text.",
            ),
            NodeConfig(
                node=ChunkDocumentNode,
                connections=[EmbedChunksNode],
                description="Split text into section-aware overlapping token chunks.",
            ),
            NodeConfig(
                node=EmbedChunksNode,
                connections=[StoreChunksNode],
                description="Embed all chunk texts in a single batched Voyage call.",
            ),
            NodeConfig(
                node=StoreChunksNode,
                connections=[],
                description="Persist ContentChunk rows with embeddings (terminal).",
            ),
        ],
    )
