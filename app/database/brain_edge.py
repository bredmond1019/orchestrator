"""BrainEdge Database Model Module

This module defines the SQLAlchemy model for storing structural `related:`
edges emitted by mev's `emit-graph` command over the company brain
(agentic-portfolio) markdown corpus. Each row represents one directed edge
from a source document to a (possibly unresolved) target reference.

This model is the traversal layer that makes the `related` ARRAY column on
`BrainDocument` (added in migration d1e2f3a4b5c6) queryable as a graph: the
structural neighborhood-expansion stage in RetrieveChunksNode walks these
rows to widen the semantic candidate set for the "brain" corpus.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from database.session import Base


class BrainEdge(Base):
    """SQLAlchemy model for a single directed `related:` edge between brain docs.

    Each edge is produced by resolving one `mev emit-graph` `edges[].to_ref`
    entry against the payload's `nodes[]` list. A resolved edge carries both
    the canonical `scope:doc_id` and bare `doc_id` of its target; an
    unresolved (dangling) edge leaves the target columns NULL rather than
    being dropped, preserving authoring intent for later resolution.
    """

    __tablename__ = "brain_edges"
    __table_args__ = (
        UniqueConstraint(
            "source_node_id", "to_ref", name="uq_brain_edges_source_node_id_to_ref"
        ),
        Index("ix_brain_edges_source_doc_id", "source_doc_id"),
        Index("ix_brain_edges_target_doc_id", "target_doc_id"),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        doc="Unique identifier for this edge row",
    )
    source_node_id = Column(
        String(512),
        nullable=False,
        doc="Canonical 'scope:doc_id' of the edge source (mev emit-graph edges[].from)",
    )
    source_doc_id = Column(
        String(256),
        nullable=False,
        doc="The source node's authored doc_id, for joining to brain_documents.doc_id",
    )
    to_ref = Column(
        String(512),
        nullable=False,
        doc="The raw authored 'related:' entry (bare doc_id or already-scoped 'scope:doc_id')",
    )
    target_node_id = Column(
        String(512),
        nullable=True,
        doc="Resolved canonical 'scope:doc_id' of the edge target; NULL when dangling",
    )
    target_doc_id = Column(
        String(256),
        nullable=True,
        doc="Resolved target doc_id, for joining to brain_documents.doc_id; NULL when dangling",
    )
    kind = Column(
        String(64),
        nullable=False,
        default="related",
        doc="Edge kind as emitted by mev (currently always 'related')",
    )
    scope = Column(
        String(128),
        nullable=True,
        doc="Optional scope of the source node (mev emit-graph nodes[].scope)",
    )
    indexed_at = Column(
        DateTime,
        default=datetime.now,
        doc="Timestamp when this edge row was last (re)loaded",
    )
