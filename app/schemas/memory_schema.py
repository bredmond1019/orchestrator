"""Event schemas for the block OR.S memory workflows.

``MemoryIngestEventSchema`` is the fast, per-interaction ingest path (Task
3). ``MemoryConsolidationEventSchema`` (Task 4) will be added here alongside
it, per the standard scaffold — one schema module per project, mirroring the
other ``app/schemas/*_schema.py`` files.
"""

from pydantic import BaseModel, Field


class MemoryIngestEventSchema(BaseModel):
    """Event schema for ``MemoryIngestWorkflow`` — one interaction to record.

    Fields:
        workspace_id: The D47 workspace name (``brain.toml`` ``[[repos]].slug``
            format) this interaction is scoped to.
        peer_id: The entity this interaction concerned — caller-supplied
            (e.g. a client slug) or a random UUID if the caller has none.
        peer_type: Entity kind — one of ``client``, ``company``, ``product``,
            ``sop``, ``user`` (mirrors ``database.peer.PeerType``).
        session_id: The session/conversation this interaction belongs to, if
            any.
        interaction: The raw interaction payload (e.g. transcript or
            free-text summary of what happened) that
            ``IngestTimeExtractionNode`` extracts from.
    """

    workspace_id: str = Field(..., description="D47 workspace name this interaction is scoped to")
    peer_id: str = Field(..., description="The entity this interaction concerned")
    peer_type: str = Field(
        ..., description="Entity kind — one of client, company, product, sop, user"
    )
    session_id: str | None = Field(
        default=None, description="The session/conversation this interaction belongs to, if any"
    )
    interaction: str = Field(
        ..., description="The raw interaction text IngestTimeExtractionNode extracts from"
    )
