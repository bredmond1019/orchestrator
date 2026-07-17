"""Tests for the assembled DocumentQAWorkflow (Project D, Task 4; DAG rewired
for the confidence-gated abstain branch in block OR.L, Task 2).

Two layers:

* **Structure** — registration, schema wiring (start node, the confidence-
  gated DAG connections) and that ``WorkflowValidator`` accepts the graph.
* **Schema** — ``DocumentQAEventSchema`` validates correctly; required fields
  are enforced; session_id is auto-generated when absent.
"""

import uuid

import pytest
from pydantic import ValidationError

from core.validate import WorkflowValidator
from schemas.document_qa_schema import DocumentQAEventSchema
from workflows.document_qa_workflow import DocumentQAWorkflow
from workflows.document_qa_workflow_nodes.abstain_node import AbstainNode
from workflows.document_qa_workflow_nodes.answer_node import AnswerNode
from workflows.document_qa_workflow_nodes.assemble_context_node import AssembleContextNode
from workflows.document_qa_workflow_nodes.embed_question_node import EmbedQuestionNode
from workflows.document_qa_workflow_nodes.grounding_router_node import (
    GroundingRouterNode,
)
from workflows.document_qa_workflow_nodes.retrieve_chunks_node import RetrieveChunksNode
from workflows.document_qa_workflow_nodes.update_session_memory_node import (
    UpdateSessionMemoryNode,
)


class TestDocumentQAWorkflowStructure:
    def test_start_is_embed_question_node(self):
        """The workflow must start at EmbedQuestionNode."""
        assert DocumentQAWorkflow.workflow_schema.start is EmbedQuestionNode

    def test_event_schema_is_document_qa(self):
        """event_schema must be DocumentQAEventSchema."""
        assert DocumentQAWorkflow.workflow_schema.event_schema is DocumentQAEventSchema

    def test_seven_nodes_in_workflow(self):
        """The workflow must contain exactly seven nodes."""
        node_classes = {nc.node for nc in DocumentQAWorkflow.workflow_schema.nodes}
        assert node_classes == {
            EmbedQuestionNode,
            RetrieveChunksNode,
            GroundingRouterNode,
            AbstainNode,
            AssembleContextNode,
            AnswerNode,
            UpdateSessionMemoryNode,
        }

    def test_dag_connections(self):
        """Connections form the confidence-gated DAG:

        Embed->Retrieve->GroundingRouter->{Abstain, Assemble}
        Abstain->Update; Assemble->Answer->Update; Update->[].
        """
        node_map = {
            nc.node: nc.connections
            for nc in DocumentQAWorkflow.workflow_schema.nodes
        }
        assert node_map[EmbedQuestionNode] == [RetrieveChunksNode]
        assert node_map[RetrieveChunksNode] == [GroundingRouterNode]
        assert node_map[GroundingRouterNode] == [AbstainNode, AssembleContextNode]
        assert node_map[AbstainNode] == [UpdateSessionMemoryNode]
        assert node_map[AssembleContextNode] == [AnswerNode]
        assert node_map[AnswerNode] == [UpdateSessionMemoryNode]
        assert node_map[UpdateSessionMemoryNode] == []

    def test_only_grounding_router_is_a_router(self):
        """Only GroundingRouterNode should be marked as a router."""
        for nc in DocumentQAWorkflow.workflow_schema.nodes:
            if nc.node is GroundingRouterNode:
                assert nc.is_router
            else:
                assert not nc.is_router

    def test_workflow_validator_accepts_schema(self):
        """WorkflowValidator must accept the workflow schema without raising."""
        validator = WorkflowValidator(DocumentQAWorkflow.workflow_schema)
        validator.validate()  # must not raise

    def test_workflow_instantiation_succeeds(self):
        """DocumentQAWorkflow() instantiates without error."""
        workflow = DocumentQAWorkflow()
        assert workflow is not None


class TestDocumentQAEventSchema:
    def test_valid_event_with_required_fields(self):
        """An event with doc_id and question validates correctly."""
        doc_id = uuid.uuid4()
        event = DocumentQAEventSchema(doc_id=doc_id, question="What is RAG?")
        assert str(event.doc_id) == str(doc_id)
        assert event.question == "What is RAG?"

    def test_session_id_generated_if_absent(self):
        """session_id is auto-generated when not supplied."""
        e1 = DocumentQAEventSchema(doc_id=uuid.uuid4(), question="Q?")
        e2 = DocumentQAEventSchema(doc_id=uuid.uuid4(), question="Q?")
        assert e1.session_id != e2.session_id

    def test_corpus_defaults_to_content(self):
        """corpus defaults to 'content'."""
        event = DocumentQAEventSchema(doc_id=uuid.uuid4(), question="Q?")
        assert event.corpus == "content"

    def test_corpus_can_be_brain(self):
        """corpus='brain' is a valid value."""
        event = DocumentQAEventSchema(
            doc_id=uuid.uuid4(), question="Q?", corpus="brain"
        )
        assert event.corpus == "brain"

    def test_missing_doc_id_raises(self):
        """doc_id is required; omitting it raises ValidationError."""
        with pytest.raises(ValidationError):
            DocumentQAEventSchema(question="Q?")

    def test_missing_question_raises(self):
        """question is required; omitting it raises ValidationError."""
        with pytest.raises(ValidationError):
            DocumentQAEventSchema(doc_id=uuid.uuid4())

    def test_explicit_session_id_accepted(self):
        """An explicit session_id is accepted and preserved."""
        s_id = uuid.uuid4()
        event = DocumentQAEventSchema(
            doc_id=uuid.uuid4(), question="Q?", session_id=s_id
        )
        assert event.session_id == s_id
