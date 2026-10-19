from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import PaymentCrud, TariffCrud
from app.enum import Status
from app.exceptions import InvalidTransition, PaymentNotFound, UnknownTariff
from app.schemas import PaymentCreate, PaymentRead
from app.services.pricing import PaymentCalculator


class PaymentService:
    def __init__(
        self, payments: PaymentCrud, tariffs: TariffCrud, calculator: PaymentCalculator
    ) -> None:
        self._payments = payments
        self._tariffs = tariffs
        self._calculator = calculator

    async def create(
        self, session: AsyncSession, data: PaymentCreate, idempotency_key: str | None
    ) -> tuple[PaymentRead, bool]:
        if idempotency_key is not None:
            existing = await self._payments.get_by_key(session, idempotency_key)
            if existing is not None:
                return existing, False

        tariff = await self._tariffs.get_by_id(session, data.tariff_id)
        if tariff is None:
            raise UnknownTariff(data.tariff_id)
        amounts = self._calculator.calculate(tariff.price, data.promo_code, data.installment_months)
        try:
            payment = await self._payments.create(
                session,
                data,
                amount=amounts.amount,
                discount=amounts.discount,
                schedule=amounts.schedule,
                idempotency_key=idempotency_key,
            )
            await session.commit()
        except IntegrityError:
            # The unique constraint remains authoritative after a concurrent lookup.
            await session.rollback()
            if idempotency_key is not None:
                existing = await self._payments.get_by_key(session, idempotency_key)
                if existing is not None:
                    return existing, False
            raise
        return payment, True

    async def get_by_id(self, session: AsyncSession, payment_id: int) -> PaymentRead:
        payment = await self._payments.get_by_id(session, payment_id)
        if payment is None:
            raise PaymentNotFound
        return payment

    async def change_status(self, session: AsyncSession, payment_id: int, target: Status) -> None:
        allowed_source = {
            Status.SUCCEEDED: Status.PENDING,
            Status.FAILED: Status.PENDING,
            Status.REFUNDED: Status.SUCCEEDED,
        }.get(target)
        if allowed_source is not None:
            changed = await self._payments.transition(session, payment_id, allowed_source, target)
            if changed:
                await session.commit()
                return
        await self.get_by_id(session, payment_id)
        raise InvalidTransition
