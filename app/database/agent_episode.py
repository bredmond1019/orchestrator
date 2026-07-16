"""AgentEpisode Database Model Module

This module defines the SQLAlchemy model for a single episodic memory
record — the fast, ingest-time capture of "what happened" in one
interaction with a ``Peer``. Episodes are the raw material dream-time
consolidation (``MemoryConsolidationWorkflow``) reasons over to distill
durable ``SemanticMemory`` facts (Honcho's two-stage pipeline, D25).

The ``embedding`` column uses the pgvector ``Vector`` type (the pgvector
extension is enabled by migration ``12a5c7643ab9``), matching the
``mxbai-embed-large`` 1024-dim default used elsewhere in this repo (OR.H).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from database.peer import peer_id_fk_column
from database.session import Base

EMBEDDING_DIM = 1024


class AgentEpisode(Base):
    """SQLAlchemy model for one ingest-time episodic memory record.

    Every ``MemoryIngestWorkflow`` run appends exactly one row for the peer
    the interaction concerned, capturing a summary, its outcome, free-form
    tags, and an embedding of the summary text for later cosine retrieval.
    """

    __tablename__ = "agent_episodes"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this episode",
    )
    peer_id = peer_id_fk_column(doc="The peer this episode concerns")
    session_id = Column(
        String(256),
        nullable=True,
        doc="The session/conversation this interaction belongs to, if any",
    )
    summary = Column(
        Text,
        nullable=False,
        doc="Fast extraction of what happened in this interaction",
    )
    outcome = Column(
        String(64),
        nullable=True,
        doc="Short outcome classification for this interaction (e.g. 'quoted_rate')",
    )
    tags = Column(
        JSON,
        default=list,
        doc="Free-form tags surfaced during ingest-time extraction",
    )
    embedding = Column(
        Vector(EMBEDDING_DIM),
        nullable=True,
        doc="1024-dim embedding of the summary text for cosine retrieval",
    )
    occurred_at = Column(
        DateTime,
        default=datetime.now,
        nullable=False,
        doc="Timestamp the interaction this episode records occurred",
    )
