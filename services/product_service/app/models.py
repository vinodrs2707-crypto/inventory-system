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


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_product_price_positive"),
        CheckConstraint("stock_quantity >= 0", name="ck_product_stock_not_negative"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), index=True, nullable=False)
    description = Column(Text, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False, index=True)
    brand = Column(String(100), index=True, nullable=False)
    price = Column(Float, index=True, nullable=False)
    image_url = Column(String(500), nullable=True)
    specifications = Column(Text, nullable=False, default="{}")  # stored as JSON text

    # These three are copies, kept up to date by other services later
    rating_average = Column(Float, nullable=False, default=0)
    rating_count = Column(Integer, nullable=False, default=0)
    stock_quantity = Column(Integer, nullable=False, default=0)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    category = relationship("Category", back_populates="products")


class RecentlyViewed(Base):
    __tablename__ = "recently_viewed"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    viewed_at = Column(DateTime, nullable=False, default=utcnow)

class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_refund_amount_positive"),)

    id = Column(Integer, primary_key=True, index=True)
    # one refund per reference: this is what stops a double refund
    reference = Column(String(100), unique=True, index=True, nullable=False)
    payment_id = Column(Integer, index=True, nullable=False)
    order_id = Column(Integer, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    reason = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="processed")
    created_at = Column(DateTime, nullable=False, default=utcnow)