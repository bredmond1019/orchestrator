"""Maps WorkflowRegistry enum names to their event schema classes."""

from pydantic import BaseModel
from schemas.content_pipeline_schema import ContentPipelineEventSchema
from schemas.customer_care_schema import CustomerCareEventSchema
from schemas.document_ingest_schema import DocumentIngestEventSchema
from schemas.document_qa_schema import DocumentQAEventSchema
from schemas.memory_schema import MemoryConsolidationEventSchema, MemoryIngestEventSchema
from schemas.proposal_generator_schema import ProposalGeneratorEventSchema
from schemas.research_agent_schema import ResearchAgentEventSchema
from schemas.sdlc_schema import SDLCFlowEventSchema
from workflows.workflow_registry import WorkflowRegistry

SCHEMA_MAP: dict[str, type[BaseModel]] = {
    WorkflowRegistry.CUSTOMER_CARE.name: CustomerCareEventSchema,
    WorkflowRegistry.CONTENT_PIPELINE.name: ContentPipelineEventSchema,
    WorkflowRegistry.RESEARCH_AGENT.name: ResearchAgentEventSchema,
    WorkflowRegistry.PROPOSAL_GENERATOR.name: ProposalGeneratorEventSchema,
    WorkflowRegistry.DOCUMENT_INGEST.name: DocumentIngestEventSchema,
    WorkflowRegistry.DOCUMENT_QA.name: DocumentQAEventSchema,
    WorkflowRegistry.SDLC_FLOW.name: SDLCFlowEventSchema,
    WorkflowRegistry.MEMORY_INGEST.name: MemoryIngestEventSchema,
    WorkflowRegistry.MEMORY_CONSOLIDATION.name: MemoryConsolidationEventSchema,
}
