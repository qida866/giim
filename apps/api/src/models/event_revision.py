"""追加式发布版本：记录系统何时知道了哪些报道，而非虚构发生时间。"""

import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.db.base import Base


class EventRevision(Base):
    __tablename__ = "event_revisions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    __table_args__ = (
        UniqueConstraint("event_id", "evidence_hash", name="uq_event_revision_evidence"),
    )
