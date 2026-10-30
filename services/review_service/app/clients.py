import logging

import httpx
from fastapi import HTTPException

from .config import settings

logger = logging.getLogger("reviews")
TIMEOUT = httpx.Timeout(5.0)


def _internal() -> dict:
    return {"X-Internal-Key": settings.INTERNAL_API_KEY}


def check_eligibility(user_id: int, product_id: int) -> dict:
    """Ask the Order service: did this customer receive this product?"""
    try:
        response = httpx.get(
            f"{settings.ORDER_SERVICE_URL}/orders/eligibility/review",
            params={"user_id": user_id, "product_id": product_id},
            headers=_internal(),
            timeout=TIMEOUT,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Order service is not available right now")
    if response.status_code != 200:
        logger.error("Order service returned %s", response.status_code)
        raise HTTPException(status_code=502, detail="Order service returned an error")
    return response.json()


def get_display_name(token: str) -> str:
    """Read the customer's name from the Auth service and shorten it: 'Test U.'"""
    try:
        response = httpx.get(
            f"{settings.AUTH_SERVICE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT,
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Auth service is not available right now")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Auth service returned an error")
    parts = response.json()["full_name"].split()
    if not parts:
        return "Customer"
    if len(parts) == 1:
        return parts[0][:50]
    return f"{parts[0][:50]} {parts[-1][0].upper()}."


def push_rating(product_id: int, average: float, count: int) -> bool:
    """Tell the Product service the new average. Returns True if it worked."""
    try:
        response = httpx.put(
            f"{settings.PRODUCT_SERVICE_URL}/products/{product_id}/rating",
            json={"rating_average": average, "rating_count": count},
            headers=_internal(),
            timeout=TIMEOUT,
        )
    except httpx.RequestError:
        return False
    if response.status_code in (204, 404):  # 404: product was deleted, nothing to update
        return True
    logger.error("Product service returned %s for rating", response.status_code)
    return False