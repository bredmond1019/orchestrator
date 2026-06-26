"""BrainDocument Database Model Module

This module defines the SQLAlchemy model for storing indexed chunks of the
company brain (agentic-portfolio) markdown corpus. Each row represents one
section-level chunk of a brain document, with a 1024-dim Voyage AI embedding
stored in pgvector for semantic retrieval.

This model is the write-path half of the brain RAG layer (Layer 1). The
read/query path ships with Project D (RetrieveChunksNode corpus parameter).
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, DateTime, FetchedValue, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR, UUID

from database.session import Base

EMBEDDING_DIM = 1024


class BrainDocument(Base):
    """SQLAlchemy model for a single indexed chunk of a company brain document.

    Each markdown file in the brain corpus is split by section header (H2/H3).
    Every section chunk produces one row, carrying the raw text, its embedding,
    and enough provenance to rebuild or re-index incrementally.
    """

    __tablename__ = "brain_documents"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this brain document chunk",
    )
    file_path = Column(
        String(512),
        nullable=False,
        doc="Relative path from brain repo root (e.g. 'docs/career.md')",
    )
    doc_type = Column(
        String(50),
        nullable=False,
        doc="Corpus category: decision|project|career|brand|business|content|diagnostic|memory",
    )
    section = Column(
        String(256),
        doc="H2/H3 header the chunk falls under; empty string if file has no headers",
    )
    content = Column(
        Text,
        nullable=False,
        doc="The raw chunk text (section header + body, up to ~500 tokens)",
    )
    embedding = Column(
        Vector(EMBEDDING_DIM),
        doc="1024-dim Voyage AI embedding (voyage-2) for semantic similarity search",
    )
    indexed_at = Column(
        DateTime,
        default=datetime.now,
        doc="Timestamp when this chunk was last indexed",
    )
    # Extended fields for diagnostic doc_type
    client_slug = Column(
        String(128),
        nullable=True,
        doc="Diagnostic client identifier (e.g. 'acme-sp-2026-07'); NULL for non-diagnostic docs",
    )
    workflow_patterns = Column(
        ARRAY(String),
        nullable=True,
        doc=(
            "Workflow pattern tags extracted from diagnostic docs"
            " (e.g. ['WhatsApp order tracking'])"
        ),
    )
    # OKF frontmatter fields — populated by index_brain.py from parsed YAML
    doc_id = Column(
        String(256),
        nullable=True,
        doc="OKF doc_id field (unique document identifier); derived from filename stem when absent",
    )
    layer = Column(
        ARRAY(String),
        nullable=True,
        doc="OKF layer field — which Bastion layers this doc belongs to (e.g. ['brain', 'engine'])",
    )
    project = Column(
        String(128),
        nullable=True,
        doc=(
            "OKF project field — which sub-project this doc belongs to"
            " (e.g. 'python-orchestration')"
        ),
    )
    status = Column(
        String(32),
        nullable=True,
        doc="OKF status field — document lifecycle status (e.g. 'active', 'draft', 'archived')",
    )
    keywords = Column(
        ARRAY(String),
        nullable=True,
        doc="OKF keywords field — searchable keyword tags extracted from frontmatter",
    )
    related = Column(
        ARRAY(String),
        nullable=True,
        doc="OKF related field — relative paths to related documents in the brain repo",
    )
    # Columns added in migration e2f3a4b5c6d7
    is_section_title = Column(
        Boolean,
        nullable=False,
        default=False,
        doc=(
            "True when this chunk is a section-header-only chunk (body empty or < 40 chars); "
            "enables 2x score weight in RetrieveChunksNode._fuse_and_rank"
        ),
    )
    title = Column(
        String(512),
        nullable=True,
        doc="OKF frontmatter title field; stored for FTS keyword search and citation display",
    )
    description = Column(
        Text,
        nullable=True,
        doc="OKF frontmatter description field; stored for FTS keyword search and citation display",
    )
    # Read-only: Postgres maintains this generated column automatically from
    # content/title/description/keywords. The indexer must NEVER write it (no INSERT/UPDATE).
    content_tsv = Column(
        TSVECTOR,
        nullable=True,
        server_default=FetchedValue(),
        doc=(
            "Generated tsvector over weighted title+keywords ('A') / description ('B') / "
            "content ('C'); GIN-indexed for graded Postgres full-text search"
        ),
    )
