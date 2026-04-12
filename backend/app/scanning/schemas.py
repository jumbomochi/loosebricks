import uuid
from datetime import datetime

from pydantic import BaseModel

from app.scanning.models import ScanStatus


class ScanCreate(BaseModel):
    collection_id: uuid.UUID
    photo_consent: bool = False


class ScanCreateResponse(BaseModel):
    id: uuid.UUID
    upload_url: str
    s3_key: str


class ScanResultResponse(BaseModel):
    id: uuid.UUID
    part_num: str
    color_id: int
    confidence: float
    bbox: dict | None
    user_verified: bool
    needs_review: bool

    model_config = {"from_attributes": True}


class ScanResponse(BaseModel):
    id: uuid.UUID
    collection_id: uuid.UUID
    status: ScanStatus
    created_at: datetime
    results: list[ScanResultResponse] = []

    model_config = {"from_attributes": True}


class ScanConfirmItem(BaseModel):
    scan_result_id: uuid.UUID
    corrected_part_num: str | None = None
    corrected_color_id: int | None = None
    accepted: bool = True


class ScanConfirmRequest(BaseModel):
    items: list[ScanConfirmItem]
