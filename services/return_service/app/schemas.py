from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

ReturnReason = Literal[
    "damaged", "defective", "wrong_item", "not_as_described", "changed_mind", "other"
]


class ReturnItemIn(BaseModel):
    order_item_id: int = Field(ge=1)
    quantity: int = Field(ge=1, le=1000)
    reason: ReturnReason
    comment: Optional[str] = Field(default=None, max_length=500)


class ReturnCreate(BaseModel):
    order_id: int = Field(ge=1)
    items: List[ReturnItemIn] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def no_repeated_items(self):
        ids = [line.order_item_id for line in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("each item can appear only once")
        return self


class InspectionLine(BaseModel):
    order_item_id: int = Field(ge=1)
    accepted_quantity: int = Field(ge=0, le=1000)
    restock: bool = True


class StatusUpdate(BaseModel):
    status: Literal["approved", "rejected", "received", "accepted", "declined"]
    note: Optional[str] = Field(default=None, max_length=255)
    items: Optional[List[InspectionLine]] = None

    @model_validator(mode="after")
    def check_rules(self):
        if self.status in ("rejected", "declined") and not (self.note and len(self.note.strip()) >= 3):
            raise ValueError("a note is required when rejecting or declining a return")
        if self.status == "accepted" and not self.items:
            raise ValueError("items (what was accepted) are required when accepting a return")
        if self.items:
            ids = [line.order_item_id for line in self.items]
            if len(ids) != len(set(ids)):
                raise ValueError("each item can appear only once")
        return self


class ReturnItemOut(BaseModel):
    order_item_id: int
    product_id: int
    product_name: str
    quantity: int
    unit_refund: float
    reason: str
    comment: Optional[str]
    accepted_quantity: Optional[int]
    restock: Optional[bool]


class HistoryOut(BaseModel):
    status: str
    note: Optional[str]
    created_at: datetime


class ReturnOut(BaseModel):
    id: int
    return_number: str
    order_id: int
    user_id: int
    status: str
    refund_status: str
    refund_amount: float
    refund_reference: Optional[str]
    items: List[ReturnItemOut]
    history: List[HistoryOut]
    created_at: datetime
    updated_at: datetime


class ReturnSummary(BaseModel):
    id: int
    return_number: str
    order_id: int
    status: str
    refund_status: str
    refund_amount: float
    item_count: int
    created_at: datetime


class ReturnPage(BaseModel):
    items: List[ReturnSummary]
    total: int
    page: int
    page_size: int