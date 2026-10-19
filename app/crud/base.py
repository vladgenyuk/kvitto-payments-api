from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base
from app.schemas.base import BaseSchema

ModelType = TypeVar("ModelType", bound=Base)
SchemaType = TypeVar("SchemaType", bound=BaseSchema)


class CrudBase(Generic[ModelType, SchemaType]):
    def __init__(self, model: type[ModelType], schema: type[SchemaType]) -> None:
        self.model = model
        self.schema = schema

    async def get_by_id(self, session: AsyncSession, item_id: int) -> SchemaType | None:
        item = await session.get(self.model, item_id)
        return self.schema.model_validate(item) if item is not None else None

    async def get_all(self, session: AsyncSession) -> list[SchemaType]:
        items = await session.scalars(select(self.model).order_by(self.model.id))
        return [self.schema.model_validate(item) for item in items]
