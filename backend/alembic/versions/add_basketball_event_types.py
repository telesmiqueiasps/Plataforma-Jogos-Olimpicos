"""add basketball event types

Revision ID: add_basketball_event_types
Revises: 86b27f89da45
Create Date: 2026-03-20

"""
from alembic import op

revision = 'add_basketball_event_types'
down_revision = '86b27f89da45'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE game_event_type ADD VALUE IF NOT EXISTS 'point_1'")
    op.execute("ALTER TYPE game_event_type ADD VALUE IF NOT EXISTS 'point_2'")
    op.execute("ALTER TYPE game_event_type ADD VALUE IF NOT EXISTS 'free_throw'")


def downgrade():
    pass  # PostgreSQL não suporta remover valores de enum facilmente
