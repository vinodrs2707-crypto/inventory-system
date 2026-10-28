import logging

import httpx
from fastapi import HTTPException

from .config import settings

logger = logging.getLogger("payments")
TIMEOUT = httpx.Timeout(5.0)


def _headers() -> dict:
    return {"X-Internal-Key": settings.INTERNAL_API_KEY}


def get_order(order_id: int) -> dict:
    try:
        response = httpx.get(
            f"{settings.ORDER_SERVICE_URL}/orders/{order_id}",
            headers=_headers(),
            timeout=TIMEOUT,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Order service is not available right now")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Order not found")
    if response.status_code != 200:
        logger.error("Order service returned %s", response.status_code)
        raise HTTPException(status_code=502, detail="Order service returned an error")
    return response.json()


def send_payment_result(order_id: int, reference: str, outcome: str) -> str:
    """Tell the Order service the result. Returns: ok, rejected or unavailable."""
    try:
        response = httpx.post(
            f"{settings.ORDER_SERVICE_URL}/orders/{order_id}/payment-result",
            headers=_headers(),
            json={"payment_id": reference, "status": outcome},
            timeout=TIMEOUT,
        )
    except httpx.RequestError:
        return "unavailable"
    if response.status_code == 200:
        return "ok"
    if response.status_code in (400, 404, 409):
        return "rejected"
    logger.error("Order service returned %s for payment result", response.status_code)
    return "unavailable"