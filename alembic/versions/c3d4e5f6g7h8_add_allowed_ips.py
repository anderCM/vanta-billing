"""Add integrators and allowed_ips tables for IP whitelisting

Revision ID: c3d4e5f6g7h8
Revises: b2c3d4e5f6g7
Create Date: 2026-03-04
"""

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6g7h8"
down_revision = "b2c3d4e5f6g7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integrators",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "allowed_ips",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("integrator_id", sa.Integer(), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["integrator_id"], ["integrators.id"]),
        sa.UniqueConstraint("ip_address"),
    )
    op.create_index("ix_allowed_ips_ip_address", "allowed_ips", ["ip_address"])

    op.add_column("clients", sa.Column("integrator_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_clients_integrator_id",
        "clients",
        "integrators",
        ["integrator_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_clients_integrator_id", "clients", type_="foreignkey")
    op.drop_column("clients", "integrator_id")
    op.drop_index("ix_allowed_ips_ip_address", table_name="allowed_ips")
    op.drop_table("allowed_ips")
    op.drop_table("integrators")
