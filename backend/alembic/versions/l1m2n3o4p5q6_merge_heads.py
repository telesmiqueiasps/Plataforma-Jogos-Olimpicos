"""merge heads

Revision ID: l1m2n3o4p5q6
Revises: c7c33fe20a26, k1l2m3n4o5p6
Create Date: 2026-03-25 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'l1m2n3o4p5q6'
down_revision: Union[str, tuple, None] = ('c7c33fe20a26', 'k1l2m3n4o5p6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
