"""Scaffold smoke tests for the content_pipeline (Project A) workflow.

Task 9 only scaffolds the workflow and registers it — no node logic yet.
These tests guard the scaffold: registration, schema wiring, and the start node.
"""

from pydantic import BaseModel
from schemas.content_pipeline_schema import ContentPipelineEventSchema
from workflows.content_pipeline_workflow import ContentPipelineWorkflow
from workflows.content_pipeline_workflow_nodes.initial_node import InitialNode
from workflows.workflow_registry import WorkflowRegistry


def test_content_pipeline_registered() -> None:
    """CONTENT_PIPELINE maps to ContentPipelineWorkflow in the registry."""
    assert WorkflowRegistry.CONTENT_PIPELINE.value is ContentPipelineWorkflow


def test_workflow_schema_wired_to_event_schema() -> None:
    """The workflow schema references the generated event schema."""
    schema = ContentPipelineWorkflow.workflow_schema
    assert schema.event_schema is ContentPipelineEventSchema
    assert schema.start is InitialNode


def test_event_schema_is_pydantic_stub() -> None:
    """The generated event schema is a (still-empty) Pydantic model."""
    assert issubclass(ContentPipelineEventSchema, BaseModel)
    assert ContentPipelineEventSchema().model_dump() == {}


def test_workflow_instantiates() -> None:
    """The scaffolded workflow passes validation and builds its node map."""
    workflow = ContentPipelineWorkflow()
    assert InitialNode in workflow.nodes
