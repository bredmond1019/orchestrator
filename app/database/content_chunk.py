"""Content Chunk Database Model Module

This module defines the SQLAlchemy model for storing document chunks produced
by the document ingestion pipeline. Each ContentChunk represents a single
text segment from an ingested document, together with its position, optional
markdown section context, and a 1024-dim Voyage embedding written at storage time.

The ``embedding`` column uses the pgvector ``Vector`` type (the pgvector extension
is enabled by migration ``12a5c7643ab9``). The ``is_section_title`` flag drives
the 2x retrieval weight boost applied to standalone heading chunks during hybrid
re-ranking (ported from the rag-engine-rs two-stage retrieval pattern).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from database.session import Base

EMBEDDING_DIM = 1024


class ContentChunk(Base):
    """SQLAlchemy model for a single document chunk with its embedding.

    Every ingested document produces one or more rows. Each row carries the
    chunk text, its position in the source document, the markdown section it
    falls under, and the Voyage embedding written at storage time.
    """

    __tablename__ = "content_chunks"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this chunk",
    )
    doc_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        doc="Groups all chunks of one ingested document",
    )
    position = Column(
        Integer,
        nullable=False,
        doc="0-based chunk order within the document",
    )
    section_title = Column(
        String(256),
        nullable=True,
        doc="Markdown header this chunk falls under",
    )
    is_section_title = Column(
        Boolean,
        default=False,
        doc="True for a standalone heading chunk; drives the retrieval 2x weight",
    )
    content = Column(
        Text,
        nullable=False,
        doc="The chunk text content",
    )
    embedding = Column(
        Vector(EMBEDDING_DIM),
        doc="1024-dim Voyage embedding written at storage time",
    )
    created_at = Column(
        DateTime,
        default=datetime.now,
        doc="Timestamp when the chunk was created",
    )
