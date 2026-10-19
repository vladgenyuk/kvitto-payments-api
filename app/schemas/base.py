from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.const import MAX_SQLITE_ID

PositiveID = Annotated[int, Field(strict=True, gt=0, le=MAX_SQLITE_ID)]


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
