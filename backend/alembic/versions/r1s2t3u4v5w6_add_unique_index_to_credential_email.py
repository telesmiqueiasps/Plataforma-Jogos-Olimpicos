"""add unique constraint to credential email

Revision ID: r1s2t3u4v5w6
Revises: q1r2s3t4u5v6
Create Date: 2026-03-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'r1s2t3u4v5w6'
down_revision: Union[str, None] = 'q1r2s3t4u5v6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remover emails duplicados mantendo apenas o registro mais antigo (menor id)
    # para cada email, os demais recebem NULL antes de criar o índice único
    op.execute(sa.text("""
        UPDATE credentials
        SET email = NULL
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM credentials
            WHERE email IS NOT NULL
            GROUP BY email
        )
        AND email IS NOT NULL
        AND email IN (
            SELECT email
            FROM credentials
            WHERE email IS NOT NULL
            GROUP BY email
            HAVING COUNT(*) > 1
        )
    """))

    # Criar índice único parcial (exclui NULLs, que são permitidos múltiplos)
    op.create_index(
        'uq_credentials_email',
        'credentials',
        ['email'],
        unique=True,
        postgresql_where=sa.text('email IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_credentials_email', table_name='credentials')
