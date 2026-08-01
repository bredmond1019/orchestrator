"""create_retrieval_queries_table

Revision ID: b8c9d0e1f2a3
Revises: a4b5c6d7e8f9
Create Date: 2026-08-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retrieval_queries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column(
            "surface", sa.String(length=16), nullable=False, server_default="unknown"
        ),
        sa.Column("workspace_id", sa.String(length=128), nullable=True),
        sa.Column("hybrid", sa.Boolean(), nullable=False),
        sa.Column("via_mix", sa.JSON(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("top_score", sa.Float(), nullable=True),
        sa.Column("retrieval_confidence", sa.Float(), nullable=True),
        sa.Column("abstained", sa.Boolean(), nullable=False),
        sa.Column("top_doc_ids", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_retrieval_queries_created_at",
        "retrieval_queries",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_retrieval_queries_created_at", table_name="retrieval_queries")
    op.drop_table("retrieval_queries")
