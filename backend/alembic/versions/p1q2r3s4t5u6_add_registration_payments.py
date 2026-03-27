"""add registration_payments table and payment fields to credentials

Revision ID: p1q2r3s4t5u6
Revises: o1p2q3r4s5t6
Create Date: 2026-03-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


revision: str = 'p1q2r3s4t5u6'
down_revision: Union[str, None] = 'o1p2q3r4s5t6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tabela de pagamentos recebidos via webhook
    op.create_table(
        'registration_payments',
        sa.Column('id',            sa.Integer(),              nullable=False),
        sa.Column('cpf',           sa.String(14),             nullable=True),
        sa.Column('full_name',     sa.String(150),            nullable=True),
        sa.Column('email',         sa.String(200),            nullable=True),
        sa.Column('phone',         sa.String(20),             nullable=True),
        sa.Column('ticket_name',   sa.String(200),            nullable=True),
        sa.Column('modality_slug', sa.String(50),             nullable=True),
        sa.Column('amount_paid',   sa.Numeric(10, 2),         nullable=True),
        sa.Column('order_id',      sa.String(100),            nullable=True),
        sa.Column('order_status',  sa.String(50),             nullable=True),
        sa.Column('raw_data',      JSON,                      nullable=True),
        sa.Column('created_at',    sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_registration_payments_cpf',   'registration_payments', ['cpf'])
    op.create_index('ix_registration_payments_email', 'registration_payments', ['email'])

    # Campos de pagamento na tabela credentials
    op.add_column('credentials', sa.Column('payment_verified',   sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('credentials', sa.Column('payment_modalities', JSON,          nullable=True))
    op.add_column('credentials', sa.Column('payment_mismatch',   sa.Boolean(), nullable=True, server_default='false'))


def downgrade() -> None:
    op.drop_column('credentials', 'payment_mismatch')
    op.drop_column('credentials', 'payment_modalities')
    op.drop_column('credentials', 'payment_verified')
    op.drop_index('ix_registration_payments_email', table_name='registration_payments')
    op.drop_index('ix_registration_payments_cpf',   table_name='registration_payments')
    op.drop_table('registration_payments')
