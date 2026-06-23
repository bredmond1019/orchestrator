"""DocumentQAEventSchema — event payload for the Document Q&A query workflow.

Validates the inbound event for ``POST /events/`` with
``workflow_type="DOCUMENT_QA"``. The schema requires a document id and a
question; the session id defaults to a new UUID if absent so callers can
start a fresh session without generating an id client-side.
"""

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DocumentQAEventSchema(BaseModel):
    """Event schema for the Document Q&A query workflow.

    Fields:
        doc_id: The document to answer over (must exist in content_chunks).
        question: The user question text.
        session_id: Q&A session identifier; generated if absent.
        corpus: Corpus to retrieve from — ``"content"`` (content_chunks,
            the default) or ``"brain"`` (brain_documents).
    """

    doc_id: UUID = Field(..., description="Document to answer over")
    question: str = Field(..., description="The user question")
    session_id: UUID = Field(
        default_factory=uuid4,
        description="Q&A session id; new UUID if absent",
    )
    corpus: str = Field(
        default="content",
        description="'content' or 'brain'",
    )
