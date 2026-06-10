from core.schema import NodeConfig, WorkflowSchema
from core.workflow import Workflow
from schemas.content_pipeline_schema import ContentPipelineEventSchema

from workflows.content_pipeline_workflow_nodes.initial_node import InitialNode


class ContentPipelineWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description="",
        event_schema=ContentPipelineEventSchema,
        start=InitialNode,
        nodes=[
            NodeConfig(
                node=InitialNode,
                connections=[],
                description="",
                parallel_nodes=[],
            ),
        ],
    )
