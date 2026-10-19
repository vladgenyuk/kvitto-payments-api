from enum import StrEnum


class Method(StrEnum):
    CARD = "card"
    SBP = "sbp"
    INSTALLMENT = "installment"


class Status(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
