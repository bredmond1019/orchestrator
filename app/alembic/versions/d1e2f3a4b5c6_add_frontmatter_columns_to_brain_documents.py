"""add_frontmatter_columns_to_brain_documents

Adds six nullable OKF frontmatter columns to brain_documents:
  doc_id, layer, project, status, keywords, related.
Creates GIN indexes on ARRAY columns (layer, keywords) and btree
indexes on scalar filterable columns (project, status, doc_id).

Revision ID: d1e2f3a4b5c6
Revises: c4d5e6f7a8b9
Create Date: 2026-06-25

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d1e2f3a4b5c6"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the six OKF frontmatter columns plus supporting indexes."""
    op.add_column(
        "brain_documents",
        sa.Column("doc_id", sa.String(256), nullable=True),
    )
    op.add_column(
        "brain_documents",
        sa.Column("layer", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "brain_documents",
        sa.Column("project", sa.String(128), nullable=True),
    )
    op.add_column(
        "brain_documents",
        sa.Column("status", sa.String(32), nullable=True),
    )
    op.add_column(
        "brain_documents",
        sa.Column("keywords", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "brain_documents",
        sa.Column("related", postgresql.ARRAY(sa.String()), nullable=True),
    )

    # GIN indexes for ARRAY columns (fast array-containment queries)
    op.create_index(
        "ix_brain_documents_layer_gin",
        "brain_documents",
        ["layer"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_brain_documents_keywords_gin",
        "brain_documents",
        ["keywords"],
        postgresql_using="gin",
    )

    # Btree indexes for scalar filterable columns
    op.create_index("ix_brain_documents_doc_id", "brain_documents", ["doc_id"])
    op.create_index("ix_brain_documents_project", "brain_documents", ["project"])
    op.create_index("ix_brain_documents_status", "brain_documents", ["status"])


def downgrade() -> None:
    """Drop the five indexes and six frontmatter columns in reverse order."""
    op.drop_index("ix_brain_documents_status", table_name="brain_documents")
    op.drop_index("ix_brain_documents_project", table_name="brain_documents")
    op.drop_index("ix_brain_documents_doc_id", table_name="brain_documents")
    op.drop_index(
        "ix_brain_documents_keywords_gin",
        table_name="brain_documents",
        postgresql_using="gin",
    )
    op.drop_index(
        "ix_brain_documents_layer_gin",
        table_name="brain_documents",
        postgresql_using="gin",
    )

    op.drop_column("brain_documents", "related")
    op.drop_column("brain_documents", "keywords")
    op.drop_column("brain_documents", "status")
    op.drop_column("brain_documents", "project")
    op.drop_column("brain_documents", "layer")
    op.drop_column("brain_documents", "doc_id")
