"""Maps WorkflowRegistry enum names to their event schema classes."""

from pydantic import BaseModel
from schemas.document_ingest_schema import DocumentIngestEventSchema
from schemas.document_qa_schema import DocumentQAEventSchema
from schemas.memory_schema import MemoryConsolidationEventSchema, MemoryIngestEventSchema
from workflows.workflow_registry import WorkflowRegistry

SCHEMA_MAP: dict[str, type[BaseModel]] = {
    WorkflowRegistry.DOCUMENT_INGEST.name: DocumentIngestEventSchema,
    WorkflowRegistry.DOCUMENT_QA.name: DocumentQAEventSchema,
    WorkflowRegistry.MEMORY_INGEST.name: MemoryIngestEventSchema,
    WorkflowRegistry.MEMORY_CONSOLIDATION.name: MemoryConsolidationEventSchema,
}
