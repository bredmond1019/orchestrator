from enum import Enum

from workflows.customer_care_workflow import CustomerCareWorkflow


class WorkflowRegistry(Enum):
    CUSTOMER_CARE = CustomerCareWorkflow
