"""add card payment fields and cantin_pdv_config

Revision ID: s1t2u3v4w5x6
Revises: 9df29e4ee3e6
Branch Labels: None
Depends On: None

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 's1t2u3v4w5x6'
down_revision: Union[str, None] = '7d23232c73fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Novos campos em cantin_orders
    op.add_column('cantin_orders', sa.Column('original_total', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('cantin_orders', sa.Column('card_fee_percent', sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column('cantin_orders', sa.Column('card_fee_amount', sa.Numeric(precision=10, scale=2), nullable=True))

    # Nova tabela de configuração de taxas por PDV
    op.create_table(
        'cantin_pdv_config',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pdv_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('debit_fee', sa.Numeric(precision=5, scale=2), nullable=True, server_default='0.00'),
        sa.Column('credit_fee', sa.Numeric(precision=5, scale=2), nullable=True, server_default='0.00'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )

    # Inserir configuração padrão para PDV 1 e 2
    op.execute(
        "INSERT INTO cantin_pdv_config (pdv_id, debit_fee, credit_fee) VALUES (1, 0, 0), (2, 0, 0) "
        "ON CONFLICT (pdv_id) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table('cantin_pdv_config')
    op.drop_column('cantin_orders', 'card_fee_amount')
    op.drop_column('cantin_orders', 'card_fee_percent')
    op.drop_column('cantin_orders', 'original_total')
