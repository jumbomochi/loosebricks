import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    user: Mapped["User"] = relationship(back_populates="collections")
    pieces: Mapped[list["CollectionPiece"]] = relationship(back_populates="collection", cascade="all, delete-orphan")


class CollectionPiece(Base):
    __tablename__ = "collection_pieces"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collections.id"), index=True)
    part_num: Mapped[str] = mapped_column(String(50), ForeignKey("parts.part_num"))
    color_id: Mapped[int] = mapped_column(Integer, ForeignKey("colors.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    collection: Mapped["Collection"] = relationship(back_populates="pieces")
    __table_args__ = (
        UniqueConstraint("collection_id", "part_num", "color_id", name="uq_collection_part_color"),
        Index("ix_collection_pieces_lookup", "collection_id", "part_num", "color_id"),
    )
