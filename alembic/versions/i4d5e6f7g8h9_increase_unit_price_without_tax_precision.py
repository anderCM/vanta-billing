"""Increase unit_price_without_tax precision to Numeric(20, 10)

Full precision avoids rounding amplification when multiplied by quantity.
Rails sends the raw result of unit_price / 1.18 without truncation.

Revision ID: i4d5e6f7g8h9
Revises: h3c4d5e6f7g8
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "i4d5e6f7g8h9"
down_revision = "h3c4d5e6f7g8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "document_items",
        "unit_price_without_tax",
        existing_type=sa.Numeric(precision=14, scale=4),
        type_=sa.Numeric(precision=20, scale=10),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "document_items",
        "unit_price_without_tax",
        existing_type=sa.Numeric(precision=20, scale=10),
        type_=sa.Numeric(precision=14, scale=4),
        existing_nullable=True,
    )
