from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from .database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_review_user_product"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating_range"),
        CheckConstraint("status IN ('approved','hidden')", name="ck_review_status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    order_id = Column(Integer, nullable=False)  # the delivered order that proves the purchase
    reviewer_name = Column(String(100), nullable=False)  # like "Test U."
    rating = Column(Integer, nullable=False)
    title = Column(String(150), nullable=True)
    comment = Column(Text, nullable=False)
    status = Column(String(20), index=True, nullable=False, default="approved")
    moderation_note = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ProductRating(Base):
    """The average we report to the Product service, and whether it got there."""

    __tablename__ = "product_ratings"

    product_id = Column(Integer, primary_key=True)
    average = Column(Float, nullable=False, default=0)
    count = Column(Integer, nullable=False, default=0)
    synced = Column(Boolean, nullable=False, default=False, index=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(100), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)