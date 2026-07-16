"""Peer Database Model Module

This module defines the SQLAlchemy model for a memory-layer ``Peer`` — any
entity that persists and changes over time: a client, a company, a product,
an SOP, or the user themself (Honcho's multi-peer entity model, D25). A peer
is the anchor row that owns a stream of ``AgentEpisode`` rows and the
``SemanticMemory`` facts distilled from them.

Peers are scoped by ``workspace_id`` (the D47 workspace-contract name — see
``docs/workspace-contract.md``), so the same ``peer_id`` in two different
workspaces never collides in queries scoped by workspace.

This model is Brain data (block OR.S); the write/read workflows around it
live in ``app/memory/`` and ``app/workflows/memory_*``.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text

from database.session import Base


def peer_id_fk_column(doc: str, nullable: bool = False):
    """Build a ``peer_id``-referencing FK column shared by memory child tables.

    Centralizes the ``String(256) -> peers.peer_id`` foreign key definition
    used by both ``AgentEpisode.peer_id``/``SemanticMemory.peer_id`` and
    ``SemanticMemory.source_peer_id`` so the column shape only lives in one
    place.
    """
    return Column(
        String(256),
        ForeignKey("peers.peer_id"),
        nullable=nullable,
        index=not nullable,
        doc=doc,
    )


class PeerType(StrEnum):
    """Controlled vocabulary for the kind of entity a ``Peer`` represents."""

    CLIENT = "client"
    COMPANY = "company"
    PRODUCT = "product"
    SOP = "sop"
    USER = "user"


class Peer(Base):
    """SQLAlchemy model for a multi-peer memory entity.

    ``peer_id`` is the primary key and is caller-supplied (e.g. a client
    slug) or defaulted to a random UUID string when the caller has no
    natural identifier. ``representation`` is the durable, dream-time-refreshed
    summary of everything currently known about this peer; it is updated by
    ``MemoryConsolidationWorkflow``, never by ingest-time writes directly.
    """

    __tablename__ = "peers"
    __table_args__ = (
        Index("ix_peers_workspace_id_peer_type", "workspace_id", "peer_type"),
    )

    peer_id = Column(
        String(256),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="Identifier for this entity; caller-supplied (e.g. a client slug) or a random UUID",
    )
    peer_type = Column(
        String(32),
        nullable=False,
        doc="Entity kind — one of client, company, product, sop, user (PeerType)",
    )
    workspace_id = Column(
        String(256),
        nullable=False,
        doc="The D47 workspace name (brain.toml [[repos]].slug format) this peer is scoped to",
    )
    representation = Column(
        Text,
        nullable=True,
        doc="Dream-time-refreshed durable summary of everything known about this peer",
    )
    updated_at = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        doc="Timestamp this peer row was last written (episode write or consolidation)",
    )
