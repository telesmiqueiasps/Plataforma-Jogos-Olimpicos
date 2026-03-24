"""increase image_url length

Revision ID: c7c33fe20a26
Revises: 459989ffd392
Create Date: 2026-03-24 00:24:02.847915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7c33fe20a26'
down_revision: Union[str, None] = '459989ffd392'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('cantin_products', 'image_url',
        existing_type=sa.String(500),
        type_=sa.String(2000),
        existing_nullable=True)


def downgrade() -> None:
    op.alter_column('cantin_products', 'image_url',
        existing_type=sa.String(2000),
        type_=sa.String(500),
        existing_nullable=True)
