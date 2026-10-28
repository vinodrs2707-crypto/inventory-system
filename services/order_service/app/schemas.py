from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ShippingAddress(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    phone: str = Field(pattern=r"^\+?[0-9]{10,15}$")
    address_line: str = Field(min_length=5, max_length=300)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(pattern=r"^[A-Za-z0-9 -]{4,10}$")


class OrderCreate(BaseModel):
    shipping: ShippingAddress
    coupon_code: Optional[str] = Field(default=None, min_length=3, max_length=30)


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    unit_price: float
    quantity: int
    line_total: float
    cancelled_quantity: int = 0


class HistoryOut(BaseModel):
    status: str
    note: Optional[str]
    created_at: datetime


class ShippingOut(BaseModel):
    full_name: str
    phone: str
    address_line: str
    city: str
    state: str
    postal_code: str


class OrderSummary(BaseModel):
    id: int
    order_number: str
    status: str
    payment_status: str
    total_amount: float
    item_count: int
    created_at: datetime


class OrderDetail(BaseModel):
    id: int
    order_number: str
    user_id: int
    status: str
    payment_status: str
    items: List[OrderItemOut]
    subtotal: float
    discount_amount: float
    coupon_code: Optional[str]
    tax_amount: float
    shipping_amount: float
    total_amount: float
    refund_due: float = 0
    shipping: ShippingOut
    history: List[HistoryOut]
    can_cancel: bool
    cancel_reason: Optional[str]
    created_at: datetime
    updated_at: datetime


class OrderPage(BaseModel):
    items: List[OrderSummary]
    total: int
    page: int
    page_size: int


class StatusUpdate(BaseModel):
    status: Literal["processing", "shipped", "delivered"]
    note: Optional[str] = Field(default=None, max_length=255)


class CancelRequest(BaseModel):
    reason: str = Field(default="Cancelled by customer", min_length=3, max_length=255)


class CancelItemLine(BaseModel):
    item_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=1000)


class CancelItemsRequest(BaseModel):
    items: List[CancelItemLine] = Field(min_length=1, max_length=50)
    reason: str = Field(default="Items cancelled by customer", min_length=3, max_length=255)

    @model_validator(mode="after")
    def no_repeated_items(self):
        ids = [line.item_id for line in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("each item can appear only once")
        return self


class PaymentResult(BaseModel):
    payment_id: str = Field(min_length=3, max_length=100)
    status: Literal["succeeded", "failed"]