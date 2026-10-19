from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from fastapi import APIRouter

from app.crud.base import CrudBase

CrudType = TypeVar("CrudType", bound=CrudBase)


class BaseRouter(Generic[CrudType], ABC):
    def __init__(self, model_crud: CrudType, prefix: str, tag: str) -> None:
        self.model_crud = model_crud
        self.prefix = prefix
        self.router = APIRouter(tags=[tag])
        self.setup_routes()

    @abstractmethod
    def setup_routes(self) -> None:
        """Register the bound methods exposed by this resource."""
