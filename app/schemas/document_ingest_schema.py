"""Event schema for the document_ingest (Project D) workflow."""

from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class DocumentIngestEventSchema(BaseModel):
    """Inbound event for the document ingestion pipeline.

    Accepts either raw text (``content``) or base64-encoded binary bytes
    (``content_b64`` + ``mime_type``). At least one of the two content fields
    must be supplied; a ``model_validator`` enforces this constraint.

    ``doc_id`` is the stable identity used when ``ContentChunk`` rows are
    persisted; a fresh UUID is generated if the caller omits it.
    """

    doc_id: UUID = Field(
        default_factory=uuid4,
        description="Stable identity for this document's chunks",
    )
    title: str = Field(
        ...,
        description="Human-readable document title",
    )
    content: str | None = Field(
        default=None,
        description="Raw document text (text path)",
    )
    content_b64: str | None = Field(
        default=None,
        description="Base64 document bytes (binary path, e.g. PDF)",
    )
    mime_type: str = Field(
        default="text/plain",
        description="MIME type for the binary path",
    )
    chunk_size: int = Field(
        default=500,
        description="Maximum token count per chunk",
    )
    overlap: int = Field(
        default=50,
        description="Token overlap between adjacent chunks",
    )

    @model_validator(mode="after")
    def _require_content_or_b64(self) -> "DocumentIngestEventSchema":
        """Ensure at least one content source is provided."""
        if self.content is None and self.content_b64 is None:
            raise ValueError("Either 'content' or 'content_b64' must be provided")
        return self
