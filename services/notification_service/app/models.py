from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)  # empty for admin alerts
    audience = Column(String(10), nullable=False, default="user", index=True)  # user or admin
    event_type = Column(String(60), nullable=False, index=True)
    title = Column(String(150), nullable=False)
    message = Column(String(500), nullable=False)
    data = Column(Text, nullable=False, default="{}")
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    read_at = Column(DateTime, nullable=True)
    event_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)


class ProcessedEvent(Base):
    """Every event we have handled. This is what stops duplicate notifications."""

    __tablename__ = "processed_events"

    event_id = Column(String(36), primary_key=True)
    event_type = Column(String(60), nullable=False)
    processed_at = Column(DateTime, nullable=False, default=utcnow)