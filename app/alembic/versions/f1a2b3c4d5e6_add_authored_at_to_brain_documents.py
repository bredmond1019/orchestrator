"""add_authored_at_to_brain_documents

Adds a nullable ``authored_at`` DateTime column to ``brain_documents``: the
file mtime at index time, persisted by ``scripts/index_brain.py`` from the
``stat()`` call it already makes for its incremental-skip check. Distinct
from ``indexed_at`` (which ``--rebuild`` resets to ``now()`` on every upsert,
block OR.M correction 3) so ``RetrieveChunksNode._fuse_and_rank`` can decay
ranking on real authoring freshness instead of a constant.

Revision ID: f1a2b3c4d5e6
Revises: a3b4c5d6e7f8
Create Date: 2026-07-16 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable authored_at column to brain_documents."""
    op.add_column(
        "brain_documents",
        sa.Column("authored_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Drop the authored_at column from brain_documents."""
    op.drop_column("brain_documents", "authored_at")
