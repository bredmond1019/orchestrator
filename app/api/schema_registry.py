"""Maps WorkflowRegistry enum names to their event schema classes."""

from pydantic import BaseModel
from schemas.content_pipeline_schema import ContentPipelineEventSchema
from schemas.customer_care_schema import CustomerCareEventSchema
from schemas.research_agent_schema import ResearchAgentEventSchema
from workflows.workflow_registry import WorkflowRegistry

SCHEMA_MAP: dict[str, type[BaseModel]] = {
    WorkflowRegistry.CUSTOMER_CARE.name: CustomerCareEventSchema,
    WorkflowRegistry.CONTENT_PIPELINE.name: ContentPipelineEventSchema,
    WorkflowRegistry.RESEARCH_AGENT.name: ResearchAgentEventSchema,
}
