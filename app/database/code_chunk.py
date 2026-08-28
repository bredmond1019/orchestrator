"""CodeChunk Database Model Module

This module defines the SQLAlchemy model for storing indexed chunks of
source code across the fleet's repos (the `code` corpus). Each row
represents one function/class/method-boundary chunk of a source file, with
a Voyage AI embedding stored in pgvector for semantic retrieval.

The column shape deliberately mirrors `app/database/brain_document.py` so
that `_CORPUS_CONFIG` in `app/brain/retrieval_engine.py` can consume this
model through the existing query path with no new machinery: this model
supplies `content`, `embedding`, `embedding_model`, `indexed_at`, and a
generated `content_tsv`, exactly like `BrainDocument` does for the "brain"
corpus. The `section` column carries the pre-rendered citation string
(`<symbol_name> (<symbol_kind>, L<start>-<end>)`) so that the normalized
recall() result dict needs no new field to carry line-number provenance —
see block OR.P's out_of_scope: the recall envelope may not gain new keys.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, FetchedValue, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID

from database.brain_document import EMBEDDING_DIM
from database.session import Base


class CodeChunk(Base):
    """SQLAlchemy model for a single indexed chunk of source code.

    Each source file in a fleet repo is split at function/class/method
    boundaries by `app.brain.code_chunking.chunk_source`, or indexed as one
    whole-file chunk when no tree-sitter grammar is installed for its
    language. Every chunk produces one row, carrying the raw text, its
    embedding, and enough provenance (repo, file path, line range) to
    resolve a citation and to re-index incrementally.
    """

    __tablename__ = "code_chunks"
    __table_args__ = (
        UniqueConstraint(
            "repo",
            "file_path",
            "start_line",
            name="uq_code_chunks_repo_file_path_start_line",
        ),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this code chunk",
    )
    repo = Column(
        String(128),
        nullable=False,
        index=True,
        doc="The brain.toml manifest slug this file belongs to; the workspace/scoping key (OR.C)",
    )
    file_path = Column(
        String(512),
        nullable=False,
        index=True,
        doc="Repo-relative POSIX path to the source file (e.g. 'app/brain/retrieval.py')",
    )
    language = Column(
        String(32),
        nullable=False,
        index=True,
        doc="'python', 'rust', or 'unknown' for the whole-file fallback",
    )
    symbol_name = Column(
        String(256),
        nullable=True,
        doc=(
            "The function/method/class name this chunk covers "
            "('Class.method' for a method); NULL for the whole-file fallback chunk"
        ),
    )
    symbol_kind = Column(
        String(32),
        nullable=True,
        doc="'function' | 'method' | 'class' | 'module' | 'file'; NULL for the fallback chunk",
    )
    start_line = Column(
        Integer,
        nullable=False,
        doc="1-indexed, inclusive start line. Every citation resolves through this — must be exact",
    )
    end_line = Column(
        Integer,
        nullable=False,
        doc="1-indexed, inclusive end line. Every citation resolves through this — must be exact",
    )
    content = Column(
        Text,
        nullable=False,
        doc="The raw chunk text (the symbol's source, or the whole file for the fallback chunk)",
    )
    embedding = Column(
        Vector(EMBEDDING_DIM),
        doc="Voyage AI embedding for semantic similarity search; same dim as BrainDocument's",
    )
    embedding_model = Column(
        String(128),
        nullable=True,
        doc="The '{provider}:{model}' stamp (EmbeddingService.stamp) resolved at write time",
    )
    section = Column(
        String(256),
        nullable=False,
        doc=(
            "The RENDERED citation, e.g. 'parse_config (function, L120-158)'. Populated at "
            "index time by app.brain.code_chunking so the indexer and any future caller "
            "cannot disagree about its format. Rides the existing recall() 'section' field — "
            "no new field is added to the normalized result dict"
        ),
    )
    indexed_at = Column(
        DateTime,
        default=datetime.now,
        doc="Timestamp when this chunk was last indexed",
    )
    # Read-only: Postgres maintains this generated column automatically from
    # symbol_name/file_path/content. The indexer must NEVER write it (no INSERT/UPDATE).
    content_tsv = Column(
        TSVECTOR,
        nullable=True,
        server_default=FetchedValue(),
        doc=(
            "Generated tsvector over weighted symbol_name ('A') / file_path ('B') / "
            "content ('C'); GIN-indexed for graded Postgres full-text search. Weighted "
            "toward symbol_name because a code search is far more often a symbol-name "
            "search than a prose search"
        ),
    )
