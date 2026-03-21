"""add boardgame fields

Revision ID: b1c2d3e4f5a6
Revises: 40cd88c9572f
Create Date: 2026-03-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = '40cd88c9572f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adiciona campo game_type ao championship
    op.add_column('championships',
        sa.Column('game_type', sa.String(length=20), nullable=True,
                  comment='Subcategoria de tabuleiro: domino, dama, xadrez'))

    # Tabela domino_teams
    op.create_table('domino_teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('championship_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('player1_id', sa.Integer(), nullable=True),
        sa.Column('player2_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['championship_id'], ['championships.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['player1_id'], ['athletes.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['player2_id'], ['athletes.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_domino_teams_championship_id', 'domino_teams', ['championship_id'], unique=False)

    # Tabela boardgame_participants
    op.create_table('boardgame_participants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('championship_id', sa.Integer(), nullable=False),
        sa.Column('athlete_id', sa.Integer(), nullable=False),
        sa.Column('game_type', sa.String(length=20), nullable=False,
                  comment='dama ou xadrez'),
        sa.ForeignKeyConstraint(['championship_id'], ['championships.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_boardgame_participant', 'boardgame_participants',
                    ['championship_id', 'athlete_id'], unique=True)
    op.create_index(op.f('ix_boardgame_participants_championship_id'), 'boardgame_participants',
                    ['championship_id'], unique=False)
    op.create_index(op.f('ix_boardgame_participants_athlete_id'), 'boardgame_participants',
                    ['athlete_id'], unique=False)

    # Tabela boardgame_games
    op.create_table('boardgame_games',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('championship_id', sa.Integer(), nullable=False),
        sa.Column('game_type', sa.String(length=20), nullable=False,
                  comment='domino, dama, xadrez'),
        sa.Column('home_id', sa.Integer(), nullable=False,
                  comment='DominoTeam.id ou Athlete.id'),
        sa.Column('away_id', sa.Integer(), nullable=False,
                  comment='DominoTeam.id ou Athlete.id'),
        sa.Column('status', sa.String(length=20), nullable=False,
                  comment='scheduled, finished'),
        sa.Column('phase', sa.String(length=50), nullable=True,
                  comment='groups, knockout'),
        sa.Column('round_number', sa.Integer(), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('extra_data', postgresql.JSON(astext_type=sa.Text()), nullable=True,
                  comment='Detalhes: partidas de dominó, peças de dama, resultado de xadrez'),
        sa.Column('home_score', sa.Integer(), nullable=True,
                  comment='Partidas ganhas (dominó) ou pontos×10 (dama/xadrez)'),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('result', sa.String(length=20), nullable=True,
                  comment='home_win, away_win, draw'),
        sa.ForeignKeyConstraint(['championship_id'], ['championships.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_boardgame_games_championship_id', 'boardgame_games',
                    ['championship_id'], unique=False)
    op.create_index('ix_boardgame_games_game_type', 'boardgame_games',
                    ['game_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_boardgame_games_game_type', table_name='boardgame_games')
    op.drop_index('ix_boardgame_games_championship_id', table_name='boardgame_games')
    op.drop_table('boardgame_games')

    op.drop_index(op.f('ix_boardgame_participants_athlete_id'), table_name='boardgame_participants')
    op.drop_index(op.f('ix_boardgame_participants_championship_id'), table_name='boardgame_participants')
    op.drop_index('uq_boardgame_participant', table_name='boardgame_participants')
    op.drop_table('boardgame_participants')

    op.drop_index('ix_domino_teams_championship_id', table_name='domino_teams')
    op.drop_table('domino_teams')

    op.drop_column('championships', 'game_type')
