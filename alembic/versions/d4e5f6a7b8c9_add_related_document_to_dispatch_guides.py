"""Add related document fields to dispatch guides

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6g7h8
Create Date: 2026-03-08
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6g7h8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dispatch_guides",
        sa.Column("related_document_id", sa.String(), nullable=True),
    )
    op.add_column(
        "dispatch_guides",
        sa.Column("related_document_type", sa.String(length=2), nullable=True),
    )
    op.add_column(
        "dispatch_guides",
        sa.Column("related_document_number", sa.String(length=20), nullable=True),
    )
    op.create_foreign_key(
        "fk_dispatch_guides_related_document_id",
        "dispatch_guides",
        "documents",
        ["related_document_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_dispatch_guides_related_document_id",
        "dispatch_guides",
        type_="foreignkey",
    )
    op.drop_column("dispatch_guides", "related_document_number")
    op.drop_column("dispatch_guides", "related_document_type")
    op.drop_column("dispatch_guides", "related_document_id")
