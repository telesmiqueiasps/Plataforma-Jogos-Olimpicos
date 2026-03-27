"""add extra fields to registration_payments

Revision ID: q1r2s3t4u5v6
Revises: p1q2r3s4t5u6
Create Date: 2026-03-27 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'q1r2s3t4u5v6'
down_revision: Union[str, None] = 'p1q2r3s4t5u6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('registration_payments', sa.Column('ticket_number',      sa.String(50),  nullable=True))
    op.add_column('registration_payments', sa.Column('church',             sa.String(150), nullable=True))
    op.add_column('registration_payments', sa.Column('pastor_name',        sa.String(150), nullable=True))
    op.add_column('registration_payments', sa.Column('pastor_phone',       sa.String(20),  nullable=True))
    op.add_column('registration_payments', sa.Column('presbytery',         sa.String(150), nullable=True))
    op.add_column('registration_payments', sa.Column('participation_type', sa.String(20),  nullable=True))


def downgrade() -> None:
    op.drop_column('registration_payments', 'participation_type')
    op.drop_column('registration_payments', 'presbytery')
    op.drop_column('registration_payments', 'pastor_phone')
    op.drop_column('registration_payments', 'pastor_name')
    op.drop_column('registration_payments', 'church')
    op.drop_column('registration_payments', 'ticket_number')
