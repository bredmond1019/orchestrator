"""Chat Session Database Model Module

This module defines the SQLAlchemy model for storing per-document Q&A sessions.
Each ChatSession tracks the ordered conversation turns (user questions and assistant
answers) for a single document Q&A session, along with the topics surfaced across
the conversation.

Session memory is appended turn-by-turn by ``UpdateSessionMemoryNode`` after each
Q&A cycle, enabling grounded multi-turn conversations over ingested documents.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime
from sqlalchemy.dialects.postgresql import UUID

from database.session import Base


class ChatSession(Base):
    """SQLAlchemy model for a per-document Q&A conversation session.

    Each session is scoped to one ingested document (``doc_id``) and holds an
    ordered list of conversation turns as JSON. Topics surfaced across the
    conversation are accumulated in ``topics_covered``.
    """

    __tablename__ = "chat_sessions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="The Q&A session id",
    )
    doc_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        doc="The document this session is scoped to",
    )
    turns = Column(
        JSON,
        default=list,
        doc="Ordered list of {role, content} conversation turns",
    )
    topics_covered = Column(
        JSON,
        default=list,
        doc="Topics surfaced across the conversation",
    )
    created_at = Column(
        DateTime,
        default=datetime.now,
        doc="Timestamp when the session was created",
    )
    updated_at = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        doc="Timestamp when the session was last updated",
    )
