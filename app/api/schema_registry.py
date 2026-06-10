"""Maps WorkflowRegistry enum names to their event schema classes."""

from pydantic import BaseModel
from schemas.content_pipeline_schema import ContentPipelineEventSchema
from schemas.customer_care_schema import CustomerCareEventSchema
from workflows.workflow_registry import WorkflowRegistry

SCHEMA_MAP: dict[str, type[BaseModel]] = {
    WorkflowRegistry.CUSTOMER_CARE.name: CustomerCareEventSchema,
    WorkflowRegistry.CONTENT_PIPELINE.name: ContentPipelineEventSchema,
}
