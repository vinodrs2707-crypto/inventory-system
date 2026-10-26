from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    category: str = Field(min_length=2, max_length=100)
    brand: str = Field(min_length=1, max_length=100)
    price: float = Field(gt=0, le=10_000_000)
    image_url: Optional[str] = Field(default=None, max_length=500)
    specifications: Dict[str, str] = Field(default_factory=dict)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    description: Optional[str] = Field(default=None, min_length=1, max_length=5000)
    category: Optional[str] = Field(default=None, min_length=2, max_length=100)
    brand: Optional[str] = Field(default=None, min_length=1, max_length=100)
    price: Optional[float] = Field(default=None, gt=0, le=10_000_000)
    image_url: Optional[str] = Field(default=None, max_length=500)
    specifications: Optional[Dict[str, str]] = None


class ProductOut(BaseModel):
    id: int
    name: str
    description: str
    category: str
    brand: str
    price: float
    image_url: Optional[str]
    specifications: Dict[str, str]
    rating_average: float
    rating_count: int
    stock_quantity: int
    in_stock: bool
    created_at: datetime


class ProductPage(BaseModel):
    items: List[ProductOut]
    total: int
    page: int
    page_size: int


class BulkImportResult(BaseModel):
    created: int
    skipped: int
    errors: List[str]