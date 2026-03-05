"""Add dispatch guides tables and client series fields

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6g7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dispatch guides table
    op.create_table(
        "dispatch_guides",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("client_id", sa.String(), nullable=False),
        sa.Column("document_type", sa.String(length=2), nullable=False),
        sa.Column("series", sa.String(length=4), nullable=False),
        sa.Column("correlative", sa.Integer(), nullable=False),
        sa.Column("transfer_reason", sa.String(length=2), nullable=False),
        sa.Column("transport_modality", sa.String(length=2), nullable=False),
        sa.Column("transfer_date", sa.String(length=10), nullable=False),
        sa.Column("gross_weight", sa.String(length=20), nullable=False),
        sa.Column("weight_unit_code", sa.String(length=5), nullable=False),
        sa.Column("departure_address", sa.String(length=500), nullable=False),
        sa.Column("departure_ubigeo", sa.String(length=6), nullable=False),
        sa.Column("arrival_address", sa.String(length=500), nullable=False),
        sa.Column("arrival_ubigeo", sa.String(length=6), nullable=False),
        sa.Column("recipient_doc_type", sa.String(length=1), nullable=False),
        sa.Column("recipient_doc_number", sa.String(length=20), nullable=False),
        sa.Column("recipient_name", sa.String(length=255), nullable=False),
        sa.Column("carrier_ruc", sa.String(length=11), nullable=True),
        sa.Column("carrier_name", sa.String(length=255), nullable=True),
        sa.Column("vehicle_plate", sa.String(length=20), nullable=True),
        sa.Column("driver_doc_type", sa.String(length=1), nullable=True),
        sa.Column("driver_doc_number", sa.String(length=20), nullable=True),
        sa.Column("driver_name", sa.String(length=255), nullable=True),
        sa.Column("driver_license", sa.String(length=50), nullable=True),
        sa.Column("shipper_doc_type", sa.String(length=1), nullable=True),
        sa.Column("shipper_doc_number", sa.String(length=20), nullable=True),
        sa.Column("shipper_name", sa.String(length=255), nullable=True),
        sa.Column("issue_date", sa.DateTime(), nullable=False),
        sa.Column("xml_content", sa.Text(), nullable=True),
        sa.Column("xml_signed", sa.Text(), nullable=True),
        sa.Column("cdr_content", sa.Text(), nullable=True),
        sa.Column("cdr_code", sa.String(length=10), nullable=True),
        sa.Column("cdr_description", sa.Text(), nullable=True),
        sa.Column("qr_text", sa.Text(), nullable=True),
        sa.Column("qr_image", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Dispatch guide items table
    op.create_table(
        "dispatch_guide_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guide_id", sa.String(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("unit_code", sa.String(length=5), nullable=False),
        sa.ForeignKeyConstraint(["guide_id"], ["dispatch_guides.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add GR series fields to clients
    op.add_column("clients", sa.Column("serie_grr", sa.String(length=4), nullable=True))
    op.add_column("clients", sa.Column("serie_grt", sa.String(length=4), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "serie_grt")
    op.drop_column("clients", "serie_grr")
    op.drop_table("dispatch_guide_items")
    op.drop_table("dispatch_guides")
