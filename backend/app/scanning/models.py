import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ScanStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collections.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    s3_key: Mapped[str] = mapped_column(String(500))
    status: Mapped[ScanStatus] = mapped_column(Enum(ScanStatus), default=ScanStatus.PENDING)
    photo_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    user: Mapped["User"] = relationship(back_populates="scans")
    results: Mapped[list["ScanResult"]] = relationship(back_populates="scan", cascade="all, delete-orphan")


class ScanResult(Base):
    __tablename__ = "scan_results"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id"), index=True)
    part_num: Mapped[str] = mapped_column(String(50), ForeignKey("parts.part_num"))
    color_id: Mapped[int] = mapped_column(Integer, ForeignKey("colors.id"))
    confidence: Mapped[float] = mapped_column(Float)
    bbox: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    user_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    user_correction_part: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_correction_color: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scan: Mapped["Scan"] = relationship(back_populates="results")
