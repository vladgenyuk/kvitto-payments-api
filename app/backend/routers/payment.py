from typing import Annotated

from fastapi import Header, Path, Query, Response
from pydantic import EmailStr

from app.backend.deps import DatabaseSession
from app.backend.routers.base import BaseRouter
from app.const import MAX_SQLITE_ID
from app.crud import PaymentCrud
from app.enum import Status
from app.schemas import PaymentCreate, PaymentRead
from app.services import PaymentService


class PaymentRouter(BaseRouter[PaymentCrud]):
    def __init__(
        self, model_crud: PaymentCrud, service: PaymentService, prefix: str = "/payments"
    ) -> None:
        self._service = service
        super().__init__(model_crud, prefix, "Payments")

    def setup_routes(self) -> None:
        self.router.add_api_route(
            self.prefix,
            self.create,
            methods=["POST"],
            response_model=PaymentRead,
            status_code=201,
            responses={200: {"model": PaymentRead, "description": "Existing payment for this key"}},
        )
        self.router.add_api_route(
            self.prefix, self.get_filtered, methods=["GET"], response_model=list[PaymentRead]
        )
        self.router.add_api_route(
            f"{self.prefix}/{{payment_id}}",
            self.get_by_id,
            methods=["GET"],
            response_model=PaymentRead,
        )

    async def create(
        self,
        data: PaymentCreate,
        response: Response,
        session: DatabaseSession,
        idempotency_key: Annotated[
            str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)
        ] = None,
    ) -> PaymentRead:
        payment, created = await self._service.create(session, data, idempotency_key)
        response.status_code = 201 if created else 200
        return payment

    async def get_filtered(
        self,
        session: DatabaseSession,
        email: Annotated[EmailStr | None, Query()] = None,
        status: Annotated[Status | None, Query()] = None,
    ) -> list[PaymentRead]:
        return await self.model_crud.get_filtered(session, email, status)

    async def get_by_id(
        self, payment_id: Annotated[int, Path(gt=0, le=MAX_SQLITE_ID)], session: DatabaseSession
    ) -> PaymentRead:
        return await self._service.get_by_id(session, payment_id)
