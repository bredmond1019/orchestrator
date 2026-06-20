"""Scaffold smoke tests for the content_pipeline (Project A) workflow.

Task 9 only scaffolds the workflow and registers it — no node logic yet.
These tests guard the scaffold: registration, schema wiring, and the start node.
"""

from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError
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


def test_event_schema_fields_and_defaults() -> None:
    """The event schema requires `url` and defaults `make_blog` to False."""
    assert issubclass(ContentPipelineEventSchema, BaseModel)
    event = ContentPipelineEventSchema(url="https://youtu.be/abc123")
    assert event.url == "https://youtu.be/abc123"
    assert event.make_blog is False
    assert isinstance(event.artifact_id, UUID)
    assert event.timestamp.tzinfo is not None
    # make_blog can be explicitly enabled.
    assert ContentPipelineEventSchema(url="https://x.com", make_blog=True).make_blog is True
    # url is required.
    with pytest.raises(ValidationError):
        ContentPipelineEventSchema()


def test_workflow_instantiates() -> None:
    """The scaffolded workflow passes validation and builds its node map."""
    workflow = ContentPipelineWorkflow()
    assert InitialNode in workflow.nodes
