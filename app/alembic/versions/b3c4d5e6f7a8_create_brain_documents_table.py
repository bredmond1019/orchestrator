"""create_brain_documents_table

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-06-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, UUID

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brain_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("doc_type", sa.String(length=50), nullable=False),
        sa.Column("section", sa.String(length=256), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.Column("client_slug", sa.String(length=128), nullable=True),
        sa.Column("workflow_patterns", ARRAY(sa.String()), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("brain_documents")
