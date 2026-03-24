"""add cantina role

Revision ID: f1a2b3c4d5e6
Revises: e1f2g3h4i5j6
Create Date: 2026-03-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e1f2g3h4i5j6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'cantina'")


def downgrade() -> None:
    pass