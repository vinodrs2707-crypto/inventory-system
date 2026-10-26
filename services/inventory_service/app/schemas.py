from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InventoryCreate(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(default=0, ge=0, le=1_000_000)
    low_stock_threshold: int = Field(default=10, ge=0, le=1_000_000)


class StockUpdate(BaseModel):
    action: Literal["add", "deduct", "set"]
    quantity: int = Field(ge=0, le=1_000_000)
    reason: str = Field(min_length=3, max_length=255)

    @model_validator(mode="after")
    def check_quantity(self):
        if self.action in ("add", "deduct") and self.quantity < 1:
            raise ValueError("quantity must be at least 1 for add or deduct")
        return self


class ThresholdUpdate(BaseModel):
    low_stock_threshold: int = Field(ge=0, le=1_000_000)


class InventoryOut(BaseModel):
    product_id: int
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int
    low_stock_threshold: int
    low_stock: bool
    out_of_stock: bool
    updated_at: datetime


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    change_type: str
    on_hand_change: int
    reserved_change: int
    on_hand_after: int
    reserved_after: int
    reason: str
    reference: Optional[str]
    user_id: Optional[int]
    created_at: datetime


class ReservationItemIn(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=1000)


class ReservationCreate(BaseModel):
    reference: str = Field(min_length=3, max_length=100)
    items: List[ReservationItemIn] = Field(min_length=1, max_length=50)
    ttl_minutes: int = Field(default=15, ge=1, le=120)

    @model_validator(mode="after")
    def no_repeated_products(self):
        ids = [item.product_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("each product can appear only once in a reservation")
        return self


class ReleaseRequest(BaseModel):
    reason: str = Field(default="Reservation released", min_length=3, max_length=255)


class ReservationItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    quantity: int


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    status: str
    expires_at: datetime
    created_at: datetime
    items: List[ReservationItemOut]