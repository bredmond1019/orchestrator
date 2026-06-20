"""Learning Artifact Database Model Module

This module defines the SQLAlchemy model for storing learning artifacts produced
by the content pipeline. A learning artifact is the persisted, embedded record of
a single ingested source (a YouTube transcript or an extracted article) together
with its structured summary and a 1024-dim embedding written at storage time.

The ``embedding`` column uses the pgvector ``Vector`` type (the pgvector extension
is enabled by migration ``12a5c7643ab9``). Structured summary data is kept in a
JSON column, mirroring ``event.py``'s column style.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from database.session import Base

EMBEDDING_DIM = 1024


class LearningArtifact(Base):
    """SQLAlchemy model for a persisted, embedded learning artifact.

    Every ingested item produces exactly one row, regardless of whether a blog
    draft was requested. The row carries the source provenance, the structured
    ``SummaryOutput`` (as JSON), and the embedding of the summary text.
    """

    __tablename__ = "learning_artifacts"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for the learning artifact",
    )
    source_url = Column(
        String(2048),
        nullable=False,
        doc="The original YouTube or article URL that was ingested",
    )
    source_type = Column(
        String(50),
        doc="Source classification: 'youtube' or 'article'",
    )
    title = Column(String(512), doc="Human-readable title of the source content")
    category = Column(
        String(150),
        doc="Classified category (e.g. 'ai_engineering', 'physics_relativity')",
    )
    tl_dr = Column(String, doc="One-line summary of the content")
    summary = Column(JSON, doc="Full structured SummaryOutput as JSON")
    embedding = Column(
        Vector(EMBEDDING_DIM),
        doc="1024-dim embedding of the summary text (pgvector), written at storage time",
    )
    fetch_status = Column(
        String(50),
        doc="Outcome of the fetch step: 'ok', 'fallback_used', or 'failed'",
    )
    make_blog = Column(
        Boolean,
        default=False,
        doc="Whether a blog draft was requested for this artifact",
    )
    created_at = Column(
        DateTime,
        default=datetime.now,
        doc="Timestamp when the artifact was created",
    )
