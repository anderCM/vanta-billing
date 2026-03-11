"""Add unit_price_without_tax to document_items

Revision ID: h3c4d5e6f7g8
Revises: g2b3c4d5e6f7
Create Date: 2026-03-11

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "h3c4d5e6f7g8"
down_revision = "g2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_items",
        sa.Column("unit_price_without_tax", sa.Numeric(precision=14, scale=4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_items", "unit_price_without_tax")
