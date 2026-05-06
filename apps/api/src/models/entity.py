"""实体模型，描述事件中识别出的关键对象。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.event import Event, EventEntity


class Entity(Base):
    """实体模型，表示人物、组织、地点或事件类型等结构化对象。"""

    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("name", "type", name="uq_entities_name_type"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    aliases: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    wikidata_id: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    event_links: Mapped[list["EventEntity"]] = relationship(back_populates="entity", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(
        secondary="event_entities",
        back_populates="entities",
        viewonly=True,
    )

    def __repr__(self) -> str:
        """返回便于调试的实体信息。"""
        return f"Entity(id={self.id!r}, name={self.name!r}, type={self.type!r})"

