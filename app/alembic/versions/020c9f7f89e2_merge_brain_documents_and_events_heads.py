"""merge_brain_documents_and_events_heads

Revision ID: 020c9f7f89e2
Revises: b3c4d5e6f7a8, cc3ad971094e
Create Date: 2026-06-22 14:51:47.046166

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020c9f7f89e2'
down_revision: Union[str, None] = ('b3c4d5e6f7a8', 'cc3ad971094e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
