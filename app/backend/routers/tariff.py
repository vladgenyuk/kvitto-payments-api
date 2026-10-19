from app.backend.deps import DatabaseSession
from app.backend.routers.base import BaseRouter
from app.crud import TariffCrud
from app.schemas import TariffRead


class TariffRouter(BaseRouter[TariffCrud]):
    def __init__(self, model_crud: TariffCrud, prefix: str = "/tariffs") -> None:
        super().__init__(model_crud, prefix, "Tariffs")

    def setup_routes(self) -> None:
        self.router.add_api_route(
            self.prefix, self.get_all, methods=["GET"], response_model=list[TariffRead]
        )

    async def get_all(self, session: DatabaseSession) -> list[TariffRead]:
        return await self.model_crud.get_all(session)
