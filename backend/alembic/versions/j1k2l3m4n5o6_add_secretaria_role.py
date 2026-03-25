"""add secretaria role

Revision ID: j1k2l3m4n5o6
Revises: i1j2k3l4m5n6
Create Date: 2026-03-25 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'j1k2l3m4n5o6'
down_revision: Union[str, None] = 'i1j2k3l4m5n6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'secretaria'")


def downgrade() -> None:
    pass
