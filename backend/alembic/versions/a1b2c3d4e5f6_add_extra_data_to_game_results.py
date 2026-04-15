"""add extra_data to game_results

Revision ID: a1b2c3d4e5f6
Revises: 9df29e4ee3e6
Create Date: 2026-04-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9df29e4ee3e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # O campo pode já existir no banco (adicionado via SQL direto).
    # ADD COLUMN IF NOT EXISTS garante que não haverá erro de duplicata.
    op.execute(
        "ALTER TABLE game_results ADD COLUMN IF NOT EXISTS extra_data JSONB"
    )


def downgrade() -> None:
    op.drop_column('game_results', 'extra_data')
