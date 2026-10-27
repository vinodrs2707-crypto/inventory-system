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

from .database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Coupon(Base):
    __tablename__ = "coupons"
    __table_args__ = (
        CheckConstraint("discount_value > 0", name="ck_discount_positive"),
        CheckConstraint("min_purchase_amount >= 0", name="ck_min_purchase_not_negative"),
        CheckConstraint("times_redeemed >= 0", name="ck_redeemed_not_negative"),
        CheckConstraint(
            "discount_type IN ('percentage', 'fixed')", name="ck_discount_type"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, index=True, nullable=False)
    discount_type = Column(String(20), nullable=False)  # percentage or fixed
    discount_value = Column(Float, nullable=False)
    max_discount_amount = Column(Float, nullable=True)  # cap for percentage coupons
    min_purchase_amount = Column(Float, nullable=False, default=0)
    valid_from = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    total_usage_limit = Column(Integer, nullable=True)  # empty = unlimited
    per_user_limit = Column(Integer, nullable=False, default=1)
    times_redeemed = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"

    id = Column(Integer, primary_key=True, index=True)
    coupon_id = Column(Integer, ForeignKey("coupons.id"), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    # one redemption per order: this is what stops double use
    order_reference = Column(String(100), unique=True, index=True, nullable=False)
    discount_amount = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default="redeemed")  # or released
    created_at = Column(DateTime, nullable=False, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(String(100), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)