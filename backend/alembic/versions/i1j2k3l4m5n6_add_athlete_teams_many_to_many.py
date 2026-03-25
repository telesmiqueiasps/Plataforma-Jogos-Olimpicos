"""add athlete_teams many to many

Revision ID: i1j2k3l4m5n6
Revises: h1i2j3k4l5m6
Create Date: 2026-03-25 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'i1j2k3l4m5n6'
down_revision: Union[str, None] = 'h1i2j3k4l5m6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'athlete_teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('sport_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sport_id'], ['sports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_athlete_sport', 'athlete_teams', ['athlete_id', 'sport_id'], unique=True)
    op.create_index('uq_athlete_team_link', 'athlete_teams', ['athlete_id', 'team_id'], unique=True)


def downgrade() -> None:
    op.drop_index('uq_athlete_team_link', table_name='athlete_teams')
    op.drop_index('uq_athlete_sport', table_name='athlete_teams')
    op.drop_table('athlete_teams')
