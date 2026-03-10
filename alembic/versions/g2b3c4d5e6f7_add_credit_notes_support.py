"""Add credit notes support: document fields + client series

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-10

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "g2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Credit note fields on documents
    op.add_column("documents", sa.Column("credit_note_reason_code", sa.String(2), nullable=True))
    op.add_column("documents", sa.Column("credit_note_description", sa.String(500), nullable=True))
    op.add_column("documents", sa.Column("reference_document_id", sa.String(), nullable=True))
    op.add_column("documents", sa.Column("reference_document_type", sa.String(2), nullable=True))
    op.add_column("documents", sa.Column("reference_document_series", sa.String(4), nullable=True))
    op.add_column("documents", sa.Column("reference_document_correlative", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_documents_reference_document_id",
        "documents",
        "documents",
        ["reference_document_id"],
        ["id"],
    )

    # Credit note series on clients
    op.add_column("clients", sa.Column("serie_nota_credito_factura", sa.String(4), nullable=True))
    op.add_column("clients", sa.Column("serie_nota_credito_boleta", sa.String(4), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "serie_nota_credito_boleta")
    op.drop_column("clients", "serie_nota_credito_factura")
    op.drop_constraint("fk_documents_reference_document_id", "documents", type_="foreignkey")
    op.drop_column("documents", "reference_document_correlative")
    op.drop_column("documents", "reference_document_series")
    op.drop_column("documents", "reference_document_type")
    op.drop_column("documents", "reference_document_id")
    op.drop_column("documents", "credit_note_description")
    op.drop_column("documents", "credit_note_reason_code")
