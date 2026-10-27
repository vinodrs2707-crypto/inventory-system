from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CartItemAdd(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(default=1, ge=1, le=10)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=10)


class CartItemOut(BaseModel):
    item_id: int
    product_id: int
    name: str
    unit_price: float
    price_changed: bool
    quantity: int
    line_total: float
    available_quantity: Optional[int]
    issue: Optional[str]


class CartOut(BaseModel):
    items: List[CartItemOut]
    item_count: int
    subtotal: float
    has_issues: bool


class CartValidation(BaseModel):
    valid: bool
    message: str
    cart: CartOut


class WishlistAdd(BaseModel):
    product_id: int = Field(ge=1)


class WishlistItemOut(BaseModel):
    item_id: int
    product_id: int
    product_name: str
    added_at: datetime