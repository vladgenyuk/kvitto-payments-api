from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CrudBase
from app.enum import Status
from app.models import Payment
from app.schemas import PaymentCreate, PaymentRead


class PaymentCrud(CrudBase[Payment, PaymentRead]):
    def __init__(self) -> None:
        super().__init__(Payment, PaymentRead)

    async def get_by_key(self, session: AsyncSession, key: str) -> PaymentRead | None:
        item = await session.scalar(select(self.model).where(self.model.idempotency_key == key))
        return self.schema.model_validate(item) if item is not None else None

    async def get_filtered(
        self, session: AsyncSession, email: str | None = None, status: Status | None = None
    ) -> list[PaymentRead]:
        query = select(self.model).order_by(self.model.id)
        if email is not None:
            query = query.where(self.model.email == email)
        if status is not None:
            query = query.where(self.model.status == status)
        items = await session.scalars(query)
        return [self.schema.model_validate(item) for item in items]

    async def create(
        self,
        session: AsyncSession,
        data: PaymentCreate,
        *,
        amount: int,
        discount: int,
        schedule: list[int] | None,
        idempotency_key: str | None,
    ) -> PaymentRead:
        item = self.model(
            tariff_id=data.tariff_id,
            email=str(data.email),
            method=data.method,
            installment_months=data.installment_months,
            amount=amount,
            discount=discount,
            schedule=schedule,
            idempotency_key=idempotency_key,
        )
        session.add(item)
        await session.flush()
        return self.schema.model_validate(item)

    async def transition(
        self, session: AsyncSession, payment_id: int, source: Status, target: Status
    ) -> bool:
        result = await session.execute(
            update(self.model)
            .where(self.model.id == payment_id, self.model.status == source)
            .values(status=target)
            .returning(self.model.id)
        )
        return result.scalar_one_or_none() is not None
