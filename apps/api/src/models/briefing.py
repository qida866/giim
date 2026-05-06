"""简报模型，存储事件简报的版本化结果。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.event import Event


class Briefing(Base):
    """简报版本模型，记录同一事件在不同时间生成的结构化简报。"""

    __tablename__ = "briefings"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    generated_by_model: Mapped[str] = mapped_column(String(50), nullable=False)
    generation_prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    news_count_at_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    __table_args__ = (
        UniqueConstraint("event_id", "version", name="uq_briefings_event_id_version"),
        Index("ix_briefings_event_id_version_desc", event_id, version.desc()),
    )

    event: Mapped["Event"] = relationship(back_populates="briefings")

    def __repr__(self) -> str:
        """返回便于调试的简报信息。"""
        return f"Briefing(id={self.id!s}, event_id={self.event_id!s}, version={self.version!r})"

