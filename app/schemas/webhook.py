from typing import Literal

from app.enum import Status
from app.schemas.base import BaseSchema, PositiveID


class BankWebhook(BaseSchema):
    payment_id: PositiveID
    status: Status


class WebhookResult(BaseSchema):
    result: Literal["ok"] = "ok"


class TransitionError(BaseSchema):
    error: Literal["invalid_transition"] = "invalid_transition"
