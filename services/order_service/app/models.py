from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_order_total_not_negative"),
        CheckConstraint(
            "status IN ('pending','confirmed','processing','shipped','delivered','cancelled')",
            name="ck_order_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(40), unique=True, index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    status = Column(String(20), index=True, nullable=False, default="pending")
    # pending, paid, failed, refund_pending
    payment_status = Column(String(20), nullable=False, default="pending")
    payment_id = Column(String(100), nullable=True)

    subtotal = Column(Float, nullable=False)
    discount_amount = Column(Float, nullable=False, default=0)
    coupon_code = Column(String(30), nullable=True)
    tax_amount = Column(Float, nullable=False, default=0)
    shipping_amount = Column(Float, nullable=False, default=0)
    total_amount = Column(Float, nullable=False)

    reservation_id = Column(Integer, nullable=True)  # stock held in the Inventory service

    shipping_name = Column(String(150), nullable=False)
    shipping_phone = Column(String(20), nullable=False)
    shipping_address = Column(String(300), nullable=False)
    shipping_city = Column(String(100), nullable=False)
    shipping_state = Column(String(100), nullable=False)
    shipping_postal_code = Column(String(10), nullable=False)

    cancel_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    items = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )
    history = relationship(
        "OrderStatusHistory",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusHistory.id",
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_item_qty_positive"),)

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    unit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    line_total = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False)
    note = Column(String(255), nullable=True)
    changed_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    order = relationship("Order", back_populates="history")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    key = Column(String(100), nullable=False)
    order_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(100), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    

class OrderItemCancellation(Base):
    __tablename__ = "order_item_cancellations"
    __table_args__ = (
        UniqueConstraint(
            "order_id", "order_item_id", "batch_number", name="uq_cancellation_batch_item"
        ),
        CheckConstraint("quantity > 0", name="ck_cancel_qty_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    order_item_id = Column(Integer, ForeignKey("order_items.id"), nullable=False, index=True)
    batch_number = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    refund_amount = Column(Float, nullable=False)
    reason = Column(String(255), nullable=False)
    cancelled_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    order = relationship("Order", backref="cancellations")