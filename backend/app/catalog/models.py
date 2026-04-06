from sqlalchemy import ForeignKey, Index, Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Part(Base):
    __tablename__ = "parts"
    part_num: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    category_id: Mapped[int] = mapped_column(Integer)


class Color(Base):
    __tablename__ = "colors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200))
    rgb: Mapped[str] = mapped_column(String(6))
    is_trans: Mapped[bool] = mapped_column(Boolean, default=False)


class Set(Base):
    __tablename__ = "sets"
    set_num: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    year: Mapped[int] = mapped_column(Integer)
    num_parts: Mapped[int] = mapped_column(Integer)
    theme_id: Mapped[int] = mapped_column(Integer)


class SetPart(Base):
    __tablename__ = "set_parts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_num: Mapped[str] = mapped_column(String(50), ForeignKey("sets.set_num"), index=True)
    part_num: Mapped[str] = mapped_column(String(50), ForeignKey("parts.part_num"))
    color_id: Mapped[int] = mapped_column(Integer, ForeignKey("colors.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    __table_args__ = (Index("ix_set_parts_part_color", "part_num", "color_id"),)


class Moc(Base):
    __tablename__ = "mocs"
    set_num: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(500))
    designer_name: Mapped[str] = mapped_column(String(255))
    num_parts: Mapped[int] = mapped_column(Integer)


class MocPart(Base):
    __tablename__ = "moc_parts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_num: Mapped[str] = mapped_column(String(50), ForeignKey("mocs.set_num"), index=True)
    part_num: Mapped[str] = mapped_column(String(50), ForeignKey("parts.part_num"))
    color_id: Mapped[int] = mapped_column(Integer, ForeignKey("colors.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    __table_args__ = (Index("ix_moc_parts_part_color", "part_num", "color_id"),)
