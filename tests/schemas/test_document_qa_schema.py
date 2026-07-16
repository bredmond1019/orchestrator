"""Tests for DocumentQAEventSchema — Task 2 (OR.M).

Covers the new workspace_id / peer_id / include_memory fields: correct
defaults, backward compatibility (an event omitting all three still
validates), and bool coercion for include_memory.
"""

from uuid import uuid4

from schemas.document_qa_schema import DocumentQAEventSchema


class TestDocumentQAEventSchemaMemoryFields:
    def test_defaults_when_memory_fields_omitted(self):
        event = DocumentQAEventSchema(doc_id=uuid4(), question="What is X?")

        assert event.workspace_id is None
        assert event.peer_id is None
        assert event.include_memory is False

    def test_backward_compatible_with_pre_block_payload(self):
        """An event with only the original fields still validates."""
        event = DocumentQAEventSchema(
            doc_id=uuid4(),
            question="What is X?",
            corpus="brain",
            filters={"project": "orchestrator"},
            include_archived=True,
            expand_structural=False,
        )

        assert event.workspace_id is None
        assert event.peer_id is None
        assert event.include_memory is False

    def test_explicit_memory_fields_set(self):
        event = DocumentQAEventSchema(
            doc_id=uuid4(),
            question="What is X?",
            workspace_id="orchestrator",
            peer_id="peer-1",
            include_memory=True,
        )

        assert event.workspace_id == "orchestrator"
        assert event.peer_id == "peer-1"
        assert event.include_memory is True

    def test_include_memory_coerces_truthy_string(self):
        event = DocumentQAEventSchema(
            doc_id=uuid4(),
            question="What is X?",
            include_memory="true",
        )

        assert event.include_memory is True

    def test_include_memory_coerces_falsy_string(self):
        event = DocumentQAEventSchema(
            doc_id=uuid4(),
            question="What is X?",
            include_memory="false",
        )

        assert event.include_memory is False
