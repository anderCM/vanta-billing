"""Add SUNAT REST API credentials to clients

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-08
"""

from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("sunat_client_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "clients",
        sa.Column("sunat_client_secret", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "sunat_client_secret")
    op.drop_column("clients", "sunat_client_id")
