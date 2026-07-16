"""merge fts-ann and eval-tables heads

Revision ID: b7a03fc80996
Revises: e2f3a4b5c6d7, f6a7b8c9d0e1
Create Date: 2026-07-15 07:40:32.383633

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7a03fc80996'
down_revision: Union[str, None] = ('e2f3a4b5c6d7', 'f6a7b8c9d0e1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
