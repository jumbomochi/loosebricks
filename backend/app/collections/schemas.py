import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    name: str
    description: str | None = None


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class CollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    piece_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MergeRequest(BaseModel):
    source_collection_id: uuid.UUID


class PieceCreate(BaseModel):
    part_num: str
    color_id: int
    quantity: int = Field(ge=1)


class PieceUpdate(BaseModel):
    quantity: int = Field(ge=1)


class PieceResponse(BaseModel):
    id: uuid.UUID
    part_num: str
    color_id: int
    quantity: int

    model_config = {"from_attributes": True}


class PieceListResponse(BaseModel):
    items: list[PieceResponse]
    next_cursor: str | None
