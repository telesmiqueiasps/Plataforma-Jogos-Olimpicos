"""replace boardgame with domino dama xadrez sports

Revision ID: d1e2f3a4b5c6
Revises: 40cd88c9572f
Create Date: 2026-03-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE sport_slug ADD VALUE IF NOT EXISTS 'domino'")
    op.execute("ALTER TYPE sport_slug ADD VALUE IF NOT EXISTS 'dama'")
    op.execute("ALTER TYPE sport_slug ADD VALUE IF NOT EXISTS 'xadrez'")


def downgrade() -> None:
    pass
