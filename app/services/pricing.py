from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentAmounts:
    amount: int
    discount: int
    schedule: list[int] | None


class PaymentCalculator:
    def calculate(self, price: int, promo_code: str | None, months: int | None) -> PaymentAmounts:
        discount = price * 10 // 100 if promo_code is not None else 0
        amount = price - discount
        schedule = None
        if months is not None:
            base, remainder = divmod(amount, months)
            schedule = [base + (1 if index < remainder else 0) for index in range(months)]
        return PaymentAmounts(amount=amount, discount=discount, schedule=schedule)
