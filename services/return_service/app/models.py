from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ReturnRequest(Base):
    __tablename__ = "return_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('requested','approved','rejected','received','accepted','declined','refunded')",
            name="ck_return_status",
        ),
        CheckConstraint(
            "refund_status IN ('none','pending','processed','failed')",
            name="ck_return_refund_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    return_number = Column(String(40), unique=True, index=True, nullable=False)
    order_id = Column(Integer, index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    status = Column(String(20), index=True, nullable=False, default="requested")
    refund_status = Column(String(20), nullable=False, default="none")
    refund_amount = Column(Float, nullable=False, default=0)
    refund_reference = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    items = relationship(
        "ReturnItem", back_populates="request", cascade="all, delete-orphan", order_by="ReturnItem.id"
    )
    history = relationship(
        "ReturnHistory",
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="ReturnHistory.id",
    )


class ReturnItem(Base):
    __tablename__ = "return_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_return_item_qty_positive"),)

    id = Column(Integer, primary_key=True, index=True)
    return_id = Column(Integer, ForeignKey("return_requests.id"), nullable=False, index=True)
    order_item_id = Column(Integer, nullable=False, index=True)
    product_id = Column(Integer, nullable=False)
    product_name = Column(String(200), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_refund = Column(Float, nullable=False)  # money back per item, worked out by the Order service
    reason = Column(String(30), nullable=False)
    comment = Column(String(500), nullable=True)
    accepted_quantity = Column(Integer, nullable=True)  # filled in after inspection
    restock = Column(Boolean, nullable=True)  # can the accepted items be sold again?

    request = relationship("ReturnRequest", back_populates="items")


class ReturnHistory(Base):
    __tablename__ = "return_history"

    id = Column(Integer, primary_key=True, index=True)
    return_id = Column(Integer, ForeignKey("return_requests.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False)
    note = Column(String(255), nullable=True)
    changed_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    request = relationship("ReturnRequest", back_populates="history")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(100), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)