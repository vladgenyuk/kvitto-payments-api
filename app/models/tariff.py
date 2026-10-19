from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tariff(Base):
    __tablename__ = "tariffs"
    __table_args__ = (CheckConstraint("price > 0", name="positive_price"),)

    title: Mapped[str] = mapped_column(String(30), unique=True)
    price: Mapped[int] = mapped_column(Integer)
