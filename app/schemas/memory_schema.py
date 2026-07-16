"""Event schemas for the block OR.S memory workflows.

``MemoryIngestEventSchema`` is the fast, per-interaction ingest path (Task
3). ``MemoryConsolidationEventSchema`` is the dream-time consolidation path
(Task 4) — Claude-only per D35. Both live here per the standard scaffold —
one schema module per project, mirroring the other ``app/schemas/*_schema.py``
files.
"""

from datetime import datetime

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


class MemoryConsolidationEventSchema(BaseModel):
    """Event schema for ``MemoryConsolidationWorkflow`` — one dream-time pass.

    Fields:
        workspace_id: The D47 workspace name this consolidation pass is
            scoped to. Consolidation only ever reasons over peers within one
            workspace (D47 name semantics, verbatim string match).
        peer_id: When set, consolidate only this peer. When omitted (the
            common nightly-batch case), consolidate every peer in the
            workspace — the load node fans out to all of them and the
            consolidation node's structured output is keyed per peer so each
            peer's facts stay isolated within the same run.
        since: Only reason over episodes that occurred at or after this
            timestamp. When omitted, all episodes for the peer(s) are
            considered.
    """

    workspace_id: str = Field(..., description="D47 workspace name this pass is scoped to")
    peer_id: str | None = Field(
        default=None, description="Consolidate only this peer; omit for every peer in workspace"
    )
    since: datetime | None = Field(
        default=None, description="Only reason over episodes at/after this timestamp"
    )
