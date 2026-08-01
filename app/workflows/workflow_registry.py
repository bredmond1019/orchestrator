from enum import Enum

from workflows.content_pipeline_workflow import ContentPipelineWorkflow
from workflows.document_ingest_workflow import DocumentIngestWorkflow
from workflows.document_qa_workflow import DocumentQAWorkflow
from workflows.memory_consolidation_workflow import MemoryConsolidationWorkflow
from workflows.memory_ingest_workflow import MemoryIngestWorkflow
from workflows.proposal_generator_workflow import ProposalGeneratorWorkflow
from workflows.sdlc_flow_workflow import SDLCFlowWorkflow


class WorkflowRegistry(Enum):
    CONTENT_PIPELINE = ContentPipelineWorkflow
    PROPOSAL_GENERATOR = ProposalGeneratorWorkflow
    DOCUMENT_INGEST = DocumentIngestWorkflow
    DOCUMENT_QA = DocumentQAWorkflow
    SDLC_FLOW = SDLCFlowWorkflow
    MEMORY_INGEST = MemoryIngestWorkflow
    MEMORY_CONSOLIDATION = MemoryConsolidationWorkflow
