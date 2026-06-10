from enum import Enum

from workflows.content_pipeline_workflow import ContentPipelineWorkflow
from workflows.customer_care_workflow import CustomerCareWorkflow


class WorkflowRegistry(Enum):
    CUSTOMER_CARE = CustomerCareWorkflow
    CONTENT_PIPELINE = ContentPipelineWorkflow
