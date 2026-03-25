"""add credentials table

Revision ID: k1l2m3n4o5p6
Revises: j1k2l3m4n5o6
Create Date: 2026-03-25 11:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, None] = 'j1k2l3m4n5o6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('full_name', sa.String(150), nullable=False),
        sa.Column('birth_date', sa.String(10), nullable=True),
        sa.Column('cpf', sa.String(14), nullable=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('church', sa.String(150), nullable=True),
        sa.Column('pastor_name', sa.String(150), nullable=True),
        sa.Column('presbytery', sa.String(150), nullable=True),
        sa.Column('modalities', JSON, nullable=True),
        sa.Column('teams', JSON, nullable=True),
        sa.Column('status', sa.String(20), nullable=True, server_default='pending'),
        sa.Column('rejection_reason', sa.String(300), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('qr_code', sa.String(100), nullable=True),
        sa.Column('checked_in', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('checked_in_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('checked_in_by', sa.Integer(), nullable=True),
        sa.Column('wristband_type', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['checked_in_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('uq_credential_cpf', 'credentials', ['cpf'], unique=True)
    op.create_index('uq_credential_qr_code', 'credentials', ['qr_code'], unique=True)
    op.create_index('ix_credentials_status', 'credentials', ['status'])


def downgrade() -> None:
    op.drop_index('ix_credentials_status', table_name='credentials')
    op.drop_index('uq_credential_qr_code', table_name='credentials')
    op.drop_index('uq_credential_cpf', table_name='credentials')
    op.drop_table('credentials')
