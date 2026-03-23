"""add tenis_mesa sport slug

Revision ID: e1f2g3h4i5j6
Revises: d1e2f3a4b5c6
Create Date: 2026-03-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e1f2g3h4i5j6'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE sport_slug ADD VALUE IF NOT EXISTS 'tenis_mesa'")


def downgrade() -> None:
    pass
