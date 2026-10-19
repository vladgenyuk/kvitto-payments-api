from app.schemas.base import BaseSchema


class TariffRead(BaseSchema):
    id: int
    title: str
    price: int
