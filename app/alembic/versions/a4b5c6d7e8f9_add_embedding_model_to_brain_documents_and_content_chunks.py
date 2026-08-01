"""add_embedding_model_to_brain_documents_and_content_chunks

Adds a nullable ``embedding_model`` String(128) column to both
``brain_documents`` and ``content_chunks``: the ``"{provider}:{model}"``
stamp (``EmbeddingService.stamp``) resolved at write time. No
``embedding_model`` column exists anywhere today, and pgvector only rejects
wrong vector *widths* at INSERT — a same-dim model swap (e.g. two different
1024-dim models) writes silently. This column is the per-row signal the
``OR.ticket.corpus-reconcile`` deep-drift check's model-mismatch axis reads.
NULL for every pre-migration row ("unstamped", reported as informational,
never as drift).

Revision ID: a4b5c6d7e8f9
Revises: f1a2b3c4d5e6
Create Date: 2026-08-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable embedding_model column to both tables."""
    op.add_column(
        "brain_documents",
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "content_chunks",
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    """Drop the embedding_model column from both tables."""
    op.drop_column("content_chunks", "embedding_model")
    op.drop_column("brain_documents", "embedding_model")
