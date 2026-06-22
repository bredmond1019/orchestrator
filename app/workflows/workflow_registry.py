from enum import Enum

from workflows.content_pipeline_workflow import ContentPipelineWorkflow
from workflows.customer_care_workflow import CustomerCareWorkflow
from workflows.proposal_generator_workflow import ProposalGeneratorWorkflow
from workflows.research_agent_workflow import ResearchAgentWorkflow


class WorkflowRegistry(Enum):
    CUSTOMER_CARE = CustomerCareWorkflow
    CONTENT_PIPELINE = ContentPipelineWorkflow
    RESEARCH_AGENT = ResearchAgentWorkflow
    PROPOSAL_GENERATOR = ProposalGeneratorWorkflow
