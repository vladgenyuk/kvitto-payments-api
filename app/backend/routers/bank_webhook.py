from fastapi import Depends

from app.backend.deps import DatabaseSession, WebhookSignatureVerifier
from app.backend.routers.base import BaseRouter
from app.crud import PaymentCrud
from app.schemas import BankWebhook, TransitionError, WebhookResult
from app.services import PaymentService


class BankWebhookRouter(BaseRouter[PaymentCrud]):
    def __init__(
        self,
        model_crud: PaymentCrud,
        service: PaymentService,
        verifier: WebhookSignatureVerifier,
        prefix: str = "/webhooks/bank",
    ) -> None:
        self._service = service
        self._verifier = verifier
        super().__init__(model_crud, prefix, "Bank webhooks")

    def setup_routes(self) -> None:
        self.router.add_api_route(
            self.prefix,
            self.handle,
            methods=["POST"],
            response_model=WebhookResult,
            dependencies=[Depends(self._verifier)],
            responses={
                401: {"description": "Invalid or missing webhook signature"},
                404: {"description": "Payment not found"},
                409: {"model": TransitionError, "description": "Invalid status transition"},
            },
        )

    async def handle(self, data: BankWebhook, session: DatabaseSession) -> WebhookResult:
        await self._service.change_status(session, data.payment_id, data.status)
        return WebhookResult()
