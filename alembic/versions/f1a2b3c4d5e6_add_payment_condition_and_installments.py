"""Add payment_condition to documents and document_installments table

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-03-09

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("payment_condition", sa.String(10), nullable=False, server_default="contado"),
    )

    op.create_table(
        "document_installments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.String, sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("installment_number", sa.Integer, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("due_date", sa.Date, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("document_installments")
    op.drop_column("documents", "payment_condition")
