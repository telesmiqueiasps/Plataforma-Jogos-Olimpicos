"""add pdv_id to cantina tables

Revision ID: h1i2j3k4l5m6
Revises: g1h2i3j4k5l6
Create Date: 2026-03-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'h1i2j3k4l5m6'
down_revision: Union[str, None] = 'g1h2i3j4k5l6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cantin_products', sa.Column('pdv_id', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('cantin_orders', sa.Column('pdv_id', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('cantin_cash_flow', sa.Column('pdv_id', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('cantin_cash_flow', 'pdv_id')
    op.drop_column('cantin_orders', 'pdv_id')
    op.drop_column('cantin_products', 'pdv_id')
