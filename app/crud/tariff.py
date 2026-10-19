from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CrudBase
from app.models import Tariff
from app.schemas import TariffRead


class TariffCrud(CrudBase[Tariff, TariffRead]):
    def __init__(self) -> None:
        super().__init__(Tariff, TariffRead)

    async def seed(self, session: AsyncSession) -> None:
        await session.execute(
            insert(self.model)
            .values(
                [
                    {"id": 1, "title": "basic", "price": 990_000},
                    {"id": 2, "title": "standard", "price": 1_990_000},
                    {"id": 3, "title": "premium", "price": 2_990_000},
                ]
            )
            .on_conflict_do_nothing(index_elements=[self.model.id])
        )
