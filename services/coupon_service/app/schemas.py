import re
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

CODE_PATTERN = re.compile(r"^[A-Z0-9_-]{3,30}$")


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CouponCreate(BaseModel):
    code: str = Field(min_length=3, max_length=30)
    discount_type: Literal["percentage", "fixed"]
    discount_value: float = Field(gt=0, le=1_000_000)
    max_discount_amount: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    min_purchase_amount: float = Field(default=0, ge=0, le=100_000_000)
    valid_from: Optional[datetime] = None
    expires_at: datetime
    total_usage_limit: Optional[int] = Field(default=None, ge=1, le=10_000_000)
    per_user_limit: int = Field(default=1, ge=1, le=1000)

    @field_validator("code")
    @classmethod
    def clean_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not CODE_PATTERN.match(value):
            raise ValueError("code may only contain letters, numbers, - and _ (3 to 30 characters)")
        return value

    @field_validator("valid_from", "expires_at")
    @classmethod
    def fix_dates(cls, value):
        return to_naive_utc(value)

    @model_validator(mode="after")
    def check_rules(self):
        if self.discount_type == "percentage" and self.discount_value > 100:
            raise ValueError("a percentage discount cannot be more than 100")
        if self.discount_type == "fixed" and self.max_discount_amount is not None:
            raise ValueError("max_discount_amount is only for percentage coupons")
        if self.expires_at <= now_utc():
            raise ValueError("expires_at must be in the future")
        if self.valid_from is not None and self.valid_from >= self.expires_at:
            raise ValueError("valid_from must be before expires_at")
        return self


class CouponUpdate(BaseModel):
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None
    min_purchase_amount: Optional[float] = Field(default=None, ge=0, le=100_000_000)
    max_discount_amount: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    total_usage_limit: Optional[int] = Field(default=None, ge=1, le=10_000_000)
    per_user_limit: Optional[int] = Field(default=None, ge=1, le=1000)

    @field_validator("expires_at")
    @classmethod
    def fix_dates(cls, value):
        return to_naive_utc(value)


class CouponOut(BaseModel):
    id: int
    code: str
    discount_type: str
    discount_value: float
    max_discount_amount: Optional[float]
    min_purchase_amount: float
    valid_from: datetime
    expires_at: datetime
    total_usage_limit: Optional[int]
    per_user_limit: int
    times_redeemed: int
    is_active: bool
    status: str
    created_at: datetime


class CouponPage(BaseModel):
    items: List[CouponOut]
    total: int
    page: int
    page_size: int


class ValidateRequest(BaseModel):
    code: str = Field(min_length=3, max_length=30)
    cart_total: float = Field(gt=0, le=100_000_000)


class ValidateResponse(BaseModel):
    valid: bool
    code: str
    discount_type: str
    discount_amount: float
    cart_total: float
    final_total: float
    message: str


class RedeemRequest(BaseModel):
    code: str = Field(min_length=3, max_length=30)
    order_reference: str = Field(min_length=3, max_length=100)
    cart_total: float = Field(gt=0, le=100_000_000)
    user_id: int = Field(ge=1)


class RedeemResponse(BaseModel):
    order_reference: str
    code: str
    discount_amount: float
    final_total: float
    status: str