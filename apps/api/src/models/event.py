"""事件模型与关联模型，描述新闻聚类后的事件。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer, PrimaryKeyConstraint, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base

if TYPE_CHECKING:
    from src.models.briefing import Briefing
    from src.models.entity import Entity
    from src.models.news import News


class Event(Base):
    """事件聚类模型，表示由多条新闻聚合形成的业务事件。"""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    news_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    news_links: Mapped[list["EventNews"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    news: Mapped[list["News"]] = relationship(
        secondary="event_news",
        back_populates="events",
        viewonly=True,
    )
    entity_links: Mapped[list["EventEntity"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    entities: Mapped[list["Entity"]] = relationship(
        secondary="event_entities",
        back_populates="events",
        viewonly=True,
    )
    briefings: Mapped[list["Briefing"]] = relationship(back_populates="event", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """返回便于调试的事件信息。"""
        return f"Event(id={self.id!s}, title={self.title!r}, status={self.status!r})"


class EventNews(Base):
    """事件与新闻的关联模型，记录聚类分配与相似度。"""

    __tablename__ = "event_news"
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    news_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("news.id", ondelete="CASCADE"),
        nullable=False,
    )
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cluster_method: Mapped[str] = mapped_column(String(50), nullable=False, default="vector_only")
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    __table_args__ = (
        PrimaryKeyConstraint("event_id", "news_id", name="pk_event_news"),
        Index("ix_event_news_event_id_similarity_score_desc", event_id, similarity_score.desc()),
    )

    event: Mapped["Event"] = relationship(back_populates="news_links")
    news: Mapped["News"] = relationship(back_populates="event_links")

    def __repr__(self) -> str:
        """返回便于调试的事件-新闻关联信息。"""
        return f"EventNews(event_id={self.event_id!s}, news_id={self.news_id!r})"


class EventEntity(Base):
    """事件与实体的关联模型，记录实体在事件中的角色。"""

    __tablename__ = "event_entities"
    __table_args__ = (PrimaryKeyConstraint("event_id", "entity_id", "role", name="pk_event_entities"),)

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    event: Mapped["Event"] = relationship(back_populates="entity_links")
    entity: Mapped["Entity"] = relationship(back_populates="event_links")

    def __repr__(self) -> str:
        """返回便于调试的事件-实体关联信息。"""
        return f"EventEntity(event_id={self.event_id!s}, entity_id={self.entity_id!r}, role={self.role!r})"

