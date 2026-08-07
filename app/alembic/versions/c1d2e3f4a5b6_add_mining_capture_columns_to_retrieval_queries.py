"""add_mining_capture_columns_to_retrieval_queries

Revision ID: c1d2e3f4a5b6
Revises: b8c9d0e1f2a3
Create Date: 2026-08-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("retrieval_queries", sa.Column("k", sa.Integer(), nullable=True))
    op.add_column(
        "retrieval_queries", sa.Column("corpus", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "retrieval_queries",
        sa.Column("embedding_model", sa.String(length=64), nullable=True),
    )
    op.add_column("retrieval_queries", sa.Column("filters", sa.JSON(), nullable=True))
    op.add_column(
        "retrieval_queries", sa.Column("top_scores", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("retrieval_queries", "top_scores")
    op.drop_column("retrieval_queries", "filters")
    op.drop_column("retrieval_queries", "embedding_model")
    op.drop_column("retrieval_queries", "corpus")
    op.drop_column("retrieval_queries", "k")
