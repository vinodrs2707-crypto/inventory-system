import logging
from typing import List, Optional

import httpx
from fastapi import HTTPException

from .config import settings

logger = logging.getLogger("orders")
TIMEOUT = httpx.Timeout(5.0)


def _internal_headers() -> dict:
    return {"X-Internal-Key": settings.INTERNAL_API_KEY}


def _send(method: str, url: str, service: str, headers=None, json=None) -> httpx.Response:
    try:
        return httpx.request(method, url, headers=headers, json=json, timeout=TIMEOUT)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail=f"{service} is not available right now")


def _check(response: httpx.Response, service: str) -> dict:
    if response.status_code in (200, 201):
        return response.json()
    try:
        detail = response.json().get("detail")
    except Exception:
        detail = None
    if not isinstance(detail, str):
        detail = "The request was not accepted"
    if response.status_code in (400, 404, 409):
        code = 400 if response.status_code == 404 else response.status_code
        raise HTTPException(status_code=code, detail=detail)
    logger.error("%s returned %s", service, response.status_code)
    raise HTTPException(status_code=502, detail=f"{service} returned an error")


def quietly(func, *args):
    """Run a clean-up call and only log a failure (used when undoing steps)."""
    try:
        func(*args)
    except Exception:
        logger.exception("Clean-up call failed: %s", getattr(func, "__name__", "call"))


# ----- Cart service -----

def get_valid_cart(token: str) -> dict:
    response = _send(
        "POST",
        f"{settings.CART_SERVICE_URL}/cart/validate",
        "Cart service",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = _check(response, "Cart service")
    if not data["valid"]:
        raise HTTPException(status_code=400, detail=data["message"])
    return data["cart"]


def clear_cart(token: str) -> None:
    _send(
        "DELETE",
        f"{settings.CART_SERVICE_URL}/cart",
        "Cart service",
        headers={"Authorization": f"Bearer {token}"},
    )


# ----- Inventory service -----

def reserve_stock(reference: str, items: List[dict], ttl_minutes: int) -> dict:
    response = _send(
        "POST",
        f"{settings.INVENTORY_SERVICE_URL}/inventory/reservations",
        "Inventory service",
        headers=_internal_headers(),
        json={"reference": reference, "items": items, "ttl_minutes": ttl_minutes},
    )
    return _check(response, "Inventory service")


def release_reservation(reservation_id: int, reason: str) -> dict:
    response = _send(
        "POST",
        f"{settings.INVENTORY_SERVICE_URL}/inventory/reservations/{reservation_id}/release",
        "Inventory service",
        headers=_internal_headers(),
        json={"reason": reason},
    )
    return _check(response, "Inventory service")


def confirm_reservation(reservation_id: int) -> dict:
    response = _send(
        "POST",
        f"{settings.INVENTORY_SERVICE_URL}/inventory/reservations/{reservation_id}/confirm",
        "Inventory service",
        headers=_internal_headers(),
    )
    return _check(response, "Inventory service")


def restock(reference: str, items: List[dict], reason: str) -> dict:
    response = _send(
        "POST",
        f"{settings.INVENTORY_SERVICE_URL}/inventory/restock",
        "Inventory service",
        headers=_internal_headers(),
        json={"reference": reference, "items": items, "reason": reason},
    )
    return _check(response, "Inventory service")


# ----- Coupon service -----

def redeem_coupon(code: str, order_reference: str, cart_total: float, user_id: int) -> dict:
    response = _send(
        "POST",
        f"{settings.COUPON_SERVICE_URL}/coupons/redeem",
        "Coupon service",
        headers=_internal_headers(),
        json={
            "code": code,
            "order_reference": order_reference,
            "cart_total": cart_total,
            "user_id": user_id,
        },
    )
    return _check(response, "Coupon service")


def release_coupon(order_reference: str) -> Optional[dict]:
    response = _send(
        "POST",
        f"{settings.COUPON_SERVICE_URL}/coupons/redemptions/{order_reference}/release",
        "Coupon service",
        headers=_internal_headers(),
    )
    return _check(response, "Coupon service")