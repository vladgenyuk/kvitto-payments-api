class PaymentNotFound(Exception):
    pass


class UnknownTariff(Exception):
    def __init__(self, tariff_id: int) -> None:
        self.tariff_id = tariff_id
        super().__init__(f"Unknown tariff: {tariff_id}")


class InvalidTransition(Exception):
    pass
