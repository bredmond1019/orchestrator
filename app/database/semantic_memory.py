"""SemanticMemory Database Model Module

This module defines the SQLAlchemy model for a single durable fact about a
``Peer``, distilled from one or more ``AgentEpisode`` rows (dream-time
consolidation) or written directly at ingest time. Facts decay in confidence
over time (``app/memory/decay.py``) and are never overwritten in place: a
contradicting fact lowers the confidence of the contradicted row and inserts
a new row, so the full evidentiary history survives (see block OR.S
"contradictions never overwrite").

The ``embedding`` column uses the pgvector ``Vector`` type (the pgvector
extension is enabled by migration ``12a5c7643ab9``), matching the
``mxbai-embed-large`` 1024-dim default used elsewhere in this repo (OR.H).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, DateTime, Float, Text
from sqlalchemy.dialects.postgresql import UUID

from database.peer import peer_id_fk_column
from database.session import Base

EMBEDDING_DIM = 1024

DEFAULT_DECAY_FACTOR = 0.95


class SemanticMemory(Base):
    """SQLAlchemy model for one durable fact distilled about a peer.

    ``confidence`` is the fact's confidence at ``updated_at``; effective
    confidence at query time is computed on the fly via
    ``app/memory/decay.py::effective_confidence`` — this column is never
    silently aged down by a background job. ``evidence_episode_ids`` links
    the fact back to the episodes that support it. ``source_peer_id`` is set
    when a fact about one peer was derived from evidence tied to another
    peer (e.g. a company fact inferred from a client episode).
    """

    __tablename__ = "semantic_memories"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this fact",
    )
    peer_id = peer_id_fk_column(doc="The peer this fact is about")
    fact = Column(
        Text,
        nullable=False,
        doc="The distilled durable fact text",
    )
    confidence = Column(
        Float,
        nullable=False,
        doc="Confidence in this fact as of updated_at, before decay is applied",
    )
    evidence_episode_ids = Column(
        JSON,
        default=list,
        doc="List of AgentEpisode ids that support this fact",
    )
    decay_factor = Column(
        Float,
        nullable=False,
        default=DEFAULT_DECAY_FACTOR,
        doc="Per-week confidence decay multiplier applied by effective_confidence()",
    )
    source_peer_id = peer_id_fk_column(
        doc="Set when this fact about peer_id was derived from another peer's evidence",
        nullable=True,
    )
    created_at = Column(
        DateTime,
        default=datetime.now,
        doc="Timestamp this fact row was first written",
    )
    updated_at = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        doc="Timestamp this fact row's confidence was last set",
    )
    embedding = Column(
        Vector(EMBEDDING_DIM),
        nullable=True,
        doc="1024-dim embedding of the fact text for cosine retrieval",
    )
