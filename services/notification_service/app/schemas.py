from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    message: str
    data: dict
    is_read: bool
    created_at: datetime


class NotificationPage(BaseModel):
    items: List[NotificationOut]
    total: int
    unread_count: int
    page: int
    page_size: int


class HistoryItem(NotificationOut):
    user_id: Optional[int]
    audience: str


class HistoryPage(BaseModel):
    items: List[HistoryItem]
    total: int
    page: int
    page_size: int


class ReadAllResult(BaseModel):
    marked_read: int