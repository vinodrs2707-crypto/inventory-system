from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreate(BaseModel):
    # extra="forbid" means any other field (like card_number) is rejected
    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(ge=1)
    method: Literal["card", "upi", "netbanking"]
    # Only for the simulation: which result should the fake payment give?
    simulate: Literal["success", "failure", "pending"] = "success"


class PaymentOut(BaseModel):
    id: int
    reference: str
    order_id: int
    amount: float
    currency: str
    method: str
    status: str
    order_synced: bool
    failure_reason: Optional[str]
    created_at: datetime
    updated_at: datetime