"""create_learning_artifacts_table

Revision ID: a1b2c3d4e5f6
Revises: 12a5c7643ab9
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '12a5c7643ab9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learning_artifacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("category", sa.String(length=150), nullable=True),
        sa.Column("tl_dr", sa.String(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("fetch_status", sa.String(length=50), nullable=True),
        sa.Column("make_blog", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("learning_artifacts")
