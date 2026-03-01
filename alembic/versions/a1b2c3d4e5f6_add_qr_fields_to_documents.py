"""add_qr_fields_to_documents

Revision ID: a1b2c3d4e5f6
Revises: 8c7d2d1a8ac3
Create Date: 2026-02-28 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '8c7d2d1a8ac3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('documents', sa.Column('qr_text', sa.Text(), nullable=True))
    op.add_column('documents', sa.Column('qr_image', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'qr_image')
    op.drop_column('documents', 'qr_text')
