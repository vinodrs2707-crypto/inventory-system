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


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        CheckConstraint(
            "status IN ('pending','succeeded','failed','cancelled','refund_pending','refunded')",
            name="ck_payment_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(40), unique=True, index=True, nullable=False)
    order_id = Column(Integer, index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    method = Column(String(20), nullable=False)  # card, upi, netbanking (a label only)
    status = Column(String(20), index=True, nullable=False, default="pending")
    # False means the Order service has not been told the result yet
    order_synced = Column(Boolean, nullable=False, default=False)
    failure_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_pay_idempotency_user_key"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    key = Column(String(100), nullable=False)
    payment_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(100), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)