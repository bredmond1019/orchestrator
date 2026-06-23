"""Tests for the assembled document_ingest (Project D) workflow.

Two layers:

* **Structure** — registration, schema wiring (start node, linear connections)
  and that ``WorkflowValidator`` accepts the graph.
* **Schema** — ``DocumentIngestEventSchema`` validates correctly and rejects
  events that omit both content fields.
"""

import pytest
from pydantic import ValidationError

from core.validate import WorkflowValidator
from schemas.document_ingest_schema import DocumentIngestEventSchema
from workflows.document_ingest_workflow import DocumentIngestWorkflow
from workflows.document_ingest_workflow_nodes.chunk_document_node import (
    ChunkDocumentNode,
)
from workflows.document_ingest_workflow_nodes.embed_chunks_node import EmbedChunksNode
from workflows.document_ingest_workflow_nodes.parse_document_node import (
    ParseDocumentNode,
)
from workflows.document_ingest_workflow_nodes.store_chunks_node import StoreChunksNode


class TestDocumentIngestWorkflowStructure:
    def test_start_is_parse_document_node(self):
        """The workflow must start at ParseDocumentNode."""
        assert DocumentIngestWorkflow.workflow_schema.start is ParseDocumentNode

    def test_event_schema_is_document_ingest(self):
        """event_schema must be DocumentIngestEventSchema."""
        assert (
            DocumentIngestWorkflow.workflow_schema.event_schema
            is DocumentIngestEventSchema
        )

    def test_four_nodes_in_workflow(self):
        """The workflow must contain exactly four nodes."""
        node_classes = [
            nc.node for nc in DocumentIngestWorkflow.workflow_schema.nodes
        ]
        assert set(node_classes) == {
            ParseDocumentNode,
            ChunkDocumentNode,
            EmbedChunksNode,
            StoreChunksNode,
        }

    def test_linear_dag_connections(self):
        """Connections form a strict linear chain: Parse->Chunk->Embed->Store->[]."""
        node_map = {
            nc.node: nc.connections
            for nc in DocumentIngestWorkflow.workflow_schema.nodes
        }
        assert node_map[ParseDocumentNode] == [ChunkDocumentNode]
        assert node_map[ChunkDocumentNode] == [EmbedChunksNode]
        assert node_map[EmbedChunksNode] == [StoreChunksNode]
        assert node_map[StoreChunksNode] == []

    def test_no_routers(self):
        """None of the nodes should be marked as a router."""
        for nc in DocumentIngestWorkflow.workflow_schema.nodes:
            assert not nc.is_router

    def test_workflow_validator_accepts_schema(self):
        """WorkflowValidator must accept the workflow schema without raising."""
        validator = WorkflowValidator(DocumentIngestWorkflow.workflow_schema)
        validator.validate()  # must not raise

    def test_workflow_instantiation_succeeds(self):
        """DocumentIngestWorkflow() instantiates without error."""
        workflow = DocumentIngestWorkflow()
        assert workflow is not None


class TestDocumentIngestEventSchema:
    def test_text_content_validates(self):
        """An event with content= is valid."""
        event = DocumentIngestEventSchema(title="T", content="hello")
        assert event.content == "hello"
        assert event.doc_id is not None

    def test_b64_content_validates(self):
        """An event with content_b64= and mime_type= is valid."""
        import base64

        b64 = base64.b64encode(b"data").decode()
        event = DocumentIngestEventSchema(
            title="T", content_b64=b64, mime_type="text/plain"
        )
        assert event.content_b64 == b64

    def test_missing_both_content_fields_raises(self):
        """An event without content or content_b64 must raise ValidationError."""
        with pytest.raises(ValidationError, match="Either 'content' or 'content_b64'"):
            DocumentIngestEventSchema(title="T")

    def test_doc_id_generated_if_absent(self):
        """doc_id is auto-generated when not supplied."""
        e1 = DocumentIngestEventSchema(title="T", content="x")
        e2 = DocumentIngestEventSchema(title="T", content="x")
        assert e1.doc_id != e2.doc_id

    def test_defaults_are_correct(self):
        """chunk_size defaults to 500 and overlap to 50."""
        event = DocumentIngestEventSchema(title="T", content="x")
        assert event.chunk_size == 500
        assert event.overlap == 50
        assert event.mime_type == "text/plain"
