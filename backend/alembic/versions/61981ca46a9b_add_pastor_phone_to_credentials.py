"""add pastor_phone to credentials

Revision ID: 61981ca46a9b
Revises: l1m2n3o4p5q6
Create Date: 2026-03-25 20:11:11.003959

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '61981ca46a9b'
down_revision: Union[str, None] = 'l1m2n3o4p5q6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('credentials', sa.Column('pastor_phone', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('credentials', 'pastor_phone')
