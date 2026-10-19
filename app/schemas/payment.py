from datetime import datetime
from typing import Annotated, Self

from pydantic import EmailStr, Field, field_validator, model_validator

from app.enum import Method, Status
from app.schemas.base import BaseSchema, PositiveID


class PaymentCreate(BaseSchema):
    tariff_id: PositiveID
    email: EmailStr
    method: Method
    installment_months: Annotated[int, Field(strict=True)] | None = None
    promo_code: str | None = None

    @field_validator("promo_code")
    @classmethod
    def known_promo(cls, value: str | None) -> str | None:
        if value is not None and value.upper() != "KVITTO10":
            raise ValueError("Unknown promo code")
        return value

    @model_validator(mode="after")
    def valid_installment(self) -> Self:
        if self.method == Method.INSTALLMENT:
            if self.installment_months not in (3, 6, 12):
                raise ValueError("installment_months must be 3, 6 or 12 for installment")
        elif self.installment_months is not None:
            raise ValueError("installment_months is only allowed for installment")
        return self


class PaymentRead(BaseSchema):
    id: int
    status: Status
    tariff_id: int
    amount: int
    discount: int
    method: Method
    installment_months: int | None
    schedule: list[int] | None
    email: EmailStr
    created_at: datetime
