from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint("quantity_on_hand >= 0", name="ck_on_hand_not_negative"),
        CheckConstraint("quantity_reserved >= 0", name="ck_reserved_not_negative"),
        CheckConstraint(
            "quantity_reserved <= quantity_on_hand", name="ck_reserved_within_stock"
        ),
        CheckConstraint("low_stock_threshold >= 0", name="ck_threshold_not_negative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, unique=True, index=True, nullable=False)
    quantity_on_hand = Column(Integer, nullable=False, default=0)
    quantity_reserved = Column(Integer, nullable=False, default=0)
    low_stock_threshold = Column(Integer, nullable=False, default=10)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    # addition, deduction, adjustment, reservation, release, sale
    change_type = Column(String(30), nullable=False, index=True)
    on_hand_change = Column(Integer, nullable=False, default=0)
    reserved_change = Column(Integer, nullable=False, default=0)
    on_hand_after = Column(Integer, nullable=False)
    reserved_after = Column(Integer, nullable=False)
    reason = Column(String(255), nullable=False)
    reference = Column(String(100), nullable=True, index=True)
    user_id = Column(Integer, nullable=True)  # empty when another service did it
    created_at = Column(DateTime, nullable=False, default=utcnow, index=True)


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    # for example the order number; it stops duplicate reservations
    reference = Column(String(100), unique=True, index=True, nullable=False)
    # active, released, expired, confirmed
    status = Column(String(20), nullable=False, default="active", index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    items = relationship(
        "ReservationItem", back_populates="reservation", cascade="all, delete-orphan"
    )


class ReservationItem(Base):
    __tablename__ = "reservation_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_reservation_qty_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)

    reservation = relationship("Reservation", back_populates="items")