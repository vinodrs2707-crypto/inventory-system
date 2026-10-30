import logging
from typing import Optional, Tuple

import httpx
from fastapi import HTTPException

from .config import settings

logger = logging.getLogger("returns")
TIMEOUT = httpx.Timeout(5.0)


def _internal() -> dict:
    return {"X-Internal-Key": settings.INTERNAL_API_KEY}


def get_returnable(order_id: int, user_id: int) -> dict:
    """Ask the Order service what this customer can send back."""
    try:
        response = httpx.get(
            f"{settings.ORDER_SERVICE_URL}/orders/{order_id}/returnable",
            params={"user_id": user_id},
            headers=_internal(),
            timeout=TIMEOUT,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Order service is not available right now")
    if response.status_code != 200:
        logger.error("Order service returned %s", response.status_code)
        raise HTTPException(status_code=502, detail="Order service returned an error")
    return response.json()


def restock(reference: str, items: list, reason: str) -> None:
    try:
        response = httpx.post(
            f"{settings.INVENTORY_SERVICE_URL}/inventory/restock",
            json={"reference": reference, "items": items, "reason": reason},
            headers=_internal(),
            timeout=TIMEOUT,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Inventory service is not available right now")
    if response.status_code != 200:
        logger.error("Inventory service returned %s", response.status_code)
        raise HTTPException(status_code=502, detail="Inventory service could not restore the stock")


def request_refund(
    order_id: int, amount: float, reference: str, reason: str
) -> Tuple[str, Optional[str]]:
    """Returns ('ok', None), ('rejected', why) or ('unavailable', None)."""
    try:
        response = httpx.post(
            f"{settings.PAYMENT_SERVICE_URL}/payments/refunds",
            json={"order_id": order_id, "amount": amount, "reference": reference, "reason": reason},
            headers=_internal(),
            timeout=TIMEOUT,
        )
    except httpx.RequestError:
        return "unavailable", None
    if response.status_code == 200:
        return "ok", None
    if response.status_code in (400, 409):
        try:
            return "rejected", response.json().get("detail", "Refund was refused")
        except Exception:
            return "rejected", "Refund was refused"
    logger.error("Payment service returned %s for refund", response.status_code)
    return "unavailable", None