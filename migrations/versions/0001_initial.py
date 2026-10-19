"""Create tariffs and payments."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tariffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(30), nullable=False, unique=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.CheckConstraint("price > 0", name="positive_price"),
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("tariff_id", sa.Integer(), sa.ForeignKey("tariffs.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("discount", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("installment_months", sa.Integer(), nullable=True),
        sa.Column("schedule", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=True, unique=True),
        sa.CheckConstraint("amount > 0 AND discount >= 0", name="valid_money"),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')", name="valid_status"
        ),
        sa.CheckConstraint("method IN ('card', 'sbp', 'installment')", name="valid_method"),
        sa.CheckConstraint(
            "(method = 'installment' AND installment_months IS NOT NULL "
            "AND installment_months IN (3, 6, 12)) OR "
            "(method != 'installment' AND installment_months IS NULL)",
            name="valid_installment_months",
        ),
    )
    op.create_index("ix_payments_email", "payments", ["email"])


def downgrade() -> None:
    op.drop_index("ix_payments_email", table_name="payments")
    op.drop_table("payments")
    op.drop_table("tariffs")
