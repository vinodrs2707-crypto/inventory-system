from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    product_id: int = Field(ge=1)
    rating: int = Field(ge=1, le=5)
    title: Optional[str] = Field(default=None, max_length=150)
    comment: str = Field(min_length=10, max_length=2000)


class ReviewUpdate(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    title: Optional[str] = Field(default=None, max_length=150)
    comment: Optional[str] = Field(default=None, min_length=10, max_length=2000)


class ReviewOut(BaseModel):
    id: int
    product_id: int
    reviewer_name: str
    rating: int
    title: Optional[str]
    comment: str
    verified_purchase: bool = True
    is_mine: bool
    created_at: datetime
    updated_at: datetime


class MyReviewOut(ReviewOut):
    status: str
    moderation_note: Optional[str]


class RatingSummary(BaseModel):
    average: float
    count: int
    distribution: Dict[str, int]


class ProductReviewPage(BaseModel):
    summary: RatingSummary
    items: List[ReviewOut]
    total: int
    page: int
    page_size: int


class ModerationRequest(BaseModel):
    status: Literal["approved", "hidden"]
    note: Optional[str] = Field(default=None, max_length=255)


class AdminReviewOut(BaseModel):
    id: int
    product_id: int
    user_id: int
    reviewer_name: str
    rating: int
    title: Optional[str]
    comment: str
    status: str
    moderation_note: Optional[str]
    created_at: datetime
    updated_at: datetime


class AdminReviewPage(BaseModel):
    items: List[AdminReviewOut]
    total: int
    page: int
    page_size: int