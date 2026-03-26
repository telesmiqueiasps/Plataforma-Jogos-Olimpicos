"""add guardian and approval fields to credentials

Revision ID: n1o2p3q4r5s6
Revises: m1n2o3p4q5r6
Create Date: 2026-03-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'n1o2p3q4r5s6'
down_revision: Union[str, tuple, None] = 'm1n2o3p4q5r6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('credentials', sa.Column('guardian_name',    sa.String(150), nullable=True))
    op.add_column('credentials', sa.Column('guardian_phone',   sa.String(20),  nullable=True))
    op.add_column('credentials', sa.Column('is_minor',         sa.Boolean(),   nullable=True, server_default='false'))
    op.add_column('credentials', sa.Column('pastor_approved',      sa.Boolean(),              nullable=True, server_default='false'))
    op.add_column('credentials', sa.Column('pastor_approved_at',   sa.DateTime(timezone=True), nullable=True))
    op.add_column('credentials', sa.Column('pastor_approved_by',   sa.Integer(),              nullable=True))
    op.add_column('credentials', sa.Column('guardian_approved',    sa.Boolean(),              nullable=True, server_default='false'))
    op.add_column('credentials', sa.Column('guardian_approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('credentials', sa.Column('guardian_approved_by', sa.Integer(),              nullable=True))
    op.create_foreign_key(None, 'credentials', 'users', ['pastor_approved_by'],   ['id'], ondelete='SET NULL')
    op.create_foreign_key(None, 'credentials', 'users', ['guardian_approved_by'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(None, 'credentials', type_='foreignkey')
    op.drop_column('credentials', 'guardian_approved_by')
    op.drop_column('credentials', 'guardian_approved_at')
    op.drop_column('credentials', 'guardian_approved')
    op.drop_column('credentials', 'pastor_approved_by')
    op.drop_column('credentials', 'pastor_approved_at')
    op.drop_column('credentials', 'pastor_approved')
    op.drop_column('credentials', 'is_minor')
    op.drop_column('credentials', 'guardian_phone')
    op.drop_column('credentials', 'guardian_name')
