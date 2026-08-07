"""Retrieval Query Log Database Model Module

This module defines the SQLAlchemy model for ``retrieval_queries`` — one row
per call into the promoted retrieval core (``app/brain/retrieval_engine.py::
retrieve()`` and the exact-id/semantic paths in ``app/brain/retrieval.py::
recall()``). Block ``OR.K1`` exists to answer one question — "what did my
agents actually ask the Brain this week, and how often did it come up
empty?" — with a single table, a single fire-and-forget write at the single
choke point, and a single read command (``syn queries``). There is
deliberately **no aggregation table, no rollup job, and no dashboard**: the
moment this needs one, that belongs in engine-rs (the D51 guard). Any
abstain-rate or windowed statistic is computed at read time over these raw
rows — see ``app/brain/query_log.py`` and the ``syn queries`` command.

Column types are kept SQLite-compilable (``JSON`` rather than Postgres
``ARRAY``), mirroring ``eval_record.py``'s deliberate choice, so the
in-memory unit suite can create and exercise this table without Docker.
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from database.session import Base


class RetrievalQuery(Base):
    """SQLAlchemy model for a single logged retrieval-core invocation.

    One row per call into the retrieval core, regardless of which surface
    (``cli`` / ``http`` / ``workflow`` / ``mcp`` / ``unknown``) initiated it.
    Written on an independently committed session by
    ``app/brain/query_log.py::log_retrieval`` so a logging failure can never
    fail or roll back the retrieval call itself.
    """

    __tablename__ = "retrieval_queries"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this logged query",
    )
    query = Column(
        String,
        nullable=False,
        doc="The raw query text passed into the retrieval core",
    )
    surface = Column(
        String(16),
        nullable=False,
        default="unknown",
        doc="Calling surface: 'cli', 'http', 'workflow', 'eval', 'mcp', or 'unknown'",
    )
    workspace_id = Column(
        String(128),
        nullable=True,
        doc="Workspace the query was scoped to, if any",
    )
    hybrid = Column(
        Boolean,
        nullable=False,
        doc="Whether the hybrid retrieval path was used",
    )
    via_mix = Column(
        JSON,
        nullable=True,
        doc=(
            "Counts of returned candidates per 'via' value (semantic, "
            "keyword, structural, memory, exact-id)"
        ),
    )
    result_count = Column(
        Integer,
        nullable=False,
        doc="Number of candidates returned by the retrieval call",
    )
    top_score = Column(
        Float,
        nullable=True,
        doc="Score of the top-ranked candidate, if any results were returned",
    )
    retrieval_confidence = Column(
        Float,
        nullable=True,
        doc="Retrieval confidence reported for this call, if computed",
    )
    abstained = Column(
        Boolean,
        nullable=False,
        doc="Whether retrieval_confidence fell below the abstain threshold",
    )
    top_doc_ids = Column(
        JSON,
        nullable=True,
        doc="Document ids of up to the top 5 candidates, in rank order",
    )
    latency_ms = Column(
        Integer,
        nullable=True,
        doc="Wall-clock latency of the retrieval call in milliseconds",
    )
    created_at = Column(
        DateTime,
        default=datetime.now,
        index=True,
        doc="Timestamp when this query was logged",
    )
    k = Column(
        Integer,
        nullable=True,
        doc="Requested result count for this call, making result_count interpretable",
    )
    corpus = Column(
        String(32),
        nullable=True,
        doc="Corpus the query was scoped to (e.g. 'brain', 'content')",
    )
    embedding_model = Column(
        String(64),
        nullable=True,
        doc=(
            "Embedding model stamp live at call time — the only place a "
            "same-dimension model swap currently leaves a trace"
        ),
    )
    filters = Column(
        JSON,
        nullable=True,
        doc="Filters applied to this retrieval call, if any",
    )
    top_scores = Column(
        JSON,
        nullable=True,
        doc="Top 5 candidate scores, in rank order, aligned with top_doc_ids",
    )
