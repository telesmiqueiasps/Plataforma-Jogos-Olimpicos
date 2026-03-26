"""add email to credentials

Revision ID: m1n2o3p4q5r6
Revises: 61981ca46a9b
Create Date: 2026-03-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'm1n2o3p4q5r6'
down_revision: Union[str, tuple, None] = '61981ca46a9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('credentials', sa.Column('email', sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column('credentials', 'email')
