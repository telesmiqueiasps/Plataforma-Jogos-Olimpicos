"""championship phases fields

Revision ID: c1a2b3c4d5e6
Revises: a5696bb23f1f
Create Date: 2026-03-18 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c1a2b3c4d5e6'
down_revision: Union[str, None] = 'a5696bb23f1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('championships', sa.Column('teams_per_group', sa.Integer(), nullable=True))
    op.add_column('championships', sa.Column('classifieds_per_group', sa.Integer(), nullable=True))
    op.add_column('championships', sa.Column('knockout_bracket',
                  postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('championships', 'knockout_bracket')
    op.drop_column('championships', 'classifieds_per_group')
    op.drop_column('championships', 'teams_per_group')
