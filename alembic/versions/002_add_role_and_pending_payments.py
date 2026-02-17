"""Add user role and pending_payments table

Revision ID: 002
Revises: 001
Create Date: 2024-01-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(20), server_default="teacher"))
    op.create_table(
        "pending_payments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_id", sa.String(50), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column("transaction_id", sa.String(100), nullable=False),
        sa.Column("sender_name", sa.String(255), nullable=False),
        sa.Column("sender_phone", sa.String(50), nullable=True),
        sa.Column("sender_email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("admin_notes", sa.String(500), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("pending_payments")
    op.drop_column("users", "role")
