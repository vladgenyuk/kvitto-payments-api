from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from math import isfinite

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.backend.deps import WebhookSignatureVerifier
from app.backend.routers import BankWebhookRouter, PaymentRouter, TariffRouter
from app.config import Settings
from app.crud import PaymentCrud, TariffCrud
from app.db import Database
from app.exceptions import InvalidTransition, PaymentNotFound, UnknownTariff
from app.services import PaymentCalculator, PaymentService


class BackendApplication:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.app = FastAPI(title="Kvitto Payments API", version="1.0.0", lifespan=self.lifespan)
        self._setup_routes()
        self._setup_exception_handlers()

    def _setup_routes(self) -> None:
        payments = PaymentCrud()
        tariffs = TariffCrud()
        service = PaymentService(payments, tariffs, PaymentCalculator())
        verifier = WebhookSignatureVerifier(self._settings.webhook_secret)
        self.app.include_router(TariffRouter(tariffs).router)
        self.app.include_router(PaymentRouter(payments, service).router)
        self.app.include_router(BankWebhookRouter(payments, service, verifier).router)

    def _setup_exception_handlers(self) -> None:
        self.app.add_exception_handler(PaymentNotFound, self._payment_not_found)
        self.app.add_exception_handler(UnknownTariff, self._unknown_tariff)
        self.app.add_exception_handler(InvalidTransition, self._invalid_transition)
        self.app.add_exception_handler(RequestValidationError, self._validation_error)

    async def _validation_error(
        self, _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        # JSON parsing can produce inf (e.g. 1e9999); keep the 422 envelope serializable.
        detail = jsonable_encoder(
            error.errors(),
            custom_encoder={float: lambda value: value if isfinite(value) else str(value)},
        )
        return JSONResponse(status_code=422, content={"detail": detail})

    @asynccontextmanager
    async def lifespan(self, application: FastAPI) -> AsyncIterator[None]:
        database = Database(self._settings.database_url)
        application.state.database = database
        try:
            await database.initialize()
            yield
        finally:
            await database.close()

    async def _payment_not_found(self, _request: Request, _error: PaymentNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Payment not found"})

    async def _unknown_tariff(self, _request: Request, error: UnknownTariff) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {
                        "type": "value_error",
                        "loc": ["body", "tariff_id"],
                        "msg": "Value error, unknown tariff",
                        "input": error.tariff_id,
                    }
                ]
            },
        )

    async def _invalid_transition(
        self, _request: Request, _error: InvalidTransition
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "invalid_transition"})


def create_app(db_url: str | None = None, webhook_secret: str | None = None) -> FastAPI:
    return BackendApplication(Settings.from_env(db_url, webhook_secret)).app


app = create_app()
