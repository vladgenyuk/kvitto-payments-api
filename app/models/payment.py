from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.enum import Status
from app.models.base import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0 AND discount >= 0", name="valid_money"),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')",
            name="valid_status",
        ),
        CheckConstraint("method IN ('card', 'sbp', 'installment')", name="valid_method"),
        CheckConstraint(
            "(method = 'installment' AND installment_months IS NOT NULL "
            "AND installment_months IN (3, 6, 12)) OR "
            "(method != 'installment' AND installment_months IS NULL)",
            name="valid_installment_months",
        ),
    )

    status: Mapped[str] = mapped_column(String(20), default=Status.PENDING)
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"))
    amount: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(20))
    installment_months: Mapped[int | None] = mapped_column(Integer)
    schedule: Mapped[list[int] | None] = mapped_column(JSON(none_as_null=True))
    email: Mapped[str] = mapped_column(String(254), index=True)
    # Preserve UTC explicitly in SQLite, whose datetime storage has no timezone.
    created_at: Mapped[str] = mapped_column(
        String(40), default=lambda: datetime.now(UTC).isoformat()
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200), unique=True)
