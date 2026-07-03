"""create_brain_edges_table

Creates the brain_edges table, the traversal layer over BrainDocument.related.
Each row is one directed `related:` edge resolved from a mev `emit-graph`
payload: source_node_id/source_doc_id identify the edge origin, to_ref is
the raw authored reference, and target_node_id/target_doc_id are the
resolved target (NULL when the reference is dangling/unresolvable).

Adds a unique constraint on (source_node_id, to_ref) so reloading an
unchanged payload upserts instead of duplicating rows, plus non-unique
indexes on source_doc_id and target_doc_id (the traversal keys used by the
structural neighborhood-expansion retrieval stage).

Revision ID: e5f6a7b8c9d0
Revises: d1e2f3a4b5c6
Create Date: 2026-07-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create brain_edges with its unique constraint and traversal indexes."""
    op.create_table(
        "brain_edges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_node_id", sa.String(length=512), nullable=False),
        sa.Column("source_doc_id", sa.String(length=256), nullable=False),
        sa.Column("to_ref", sa.String(length=512), nullable=False),
        sa.Column("target_node_id", sa.String(length=512), nullable=True),
        sa.Column("target_doc_id", sa.String(length=256), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False, server_default="related"),
        sa.Column("scope", sa.String(length=128), nullable=True),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "source_node_id", "to_ref", name="uq_brain_edges_source_node_id_to_ref"
        ),
    )
    op.create_index(
        "ix_brain_edges_source_doc_id", "brain_edges", ["source_doc_id"]
    )
    op.create_index(
        "ix_brain_edges_target_doc_id", "brain_edges", ["target_doc_id"]
    )


def downgrade() -> None:
    """Drop the two traversal indexes and the brain_edges table."""
    op.drop_index("ix_brain_edges_target_doc_id", table_name="brain_edges")
    op.drop_index("ix_brain_edges_source_doc_id", table_name="brain_edges")
    op.drop_table("brain_edges")
