import logging
from datetime import date, datetime

import httpx
from fastapi import HTTPException

from .config import settings

logger = logging.getLogger("analytics")
TIMEOUT = httpx.Timeout(15.0)
MAX_PAGES = 50


def _get(url: str, token: str, params: dict, service: str) -> dict:
    try:
        response = httpx.get(
            url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT
        )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail=f"{service} is not available right now")
    if response.status_code in (401, 403):
        raise HTTPException(status_code=403, detail="You do not have permission to see this report")
    if response.status_code != 200:
        logger.error("%s returned %s", service, response.status_code)
        raise HTTPException(status_code=502, detail=f"{service} returned an error")
    return response.json()


def fetch_orders(token: str, date_from: date, date_to: date) -> list:
    orders = []
    for page in range(1, MAX_PAGES + 1):
        data = _get(
            f"{settings.ORDER_SERVICE_URL}/orders/reports/export",
            token,
            {
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "page": page,
                "page_size": 500,
            },
            "Order service",
        )
        orders.extend(data["orders"])
        if not data["orders"] or len(orders) >= data["total"]:
            break
    return orders


def fetch_returns(token: str, date_from: date, date_to: date) -> list:
    found = []
    for page in range(1, MAX_PAGES + 1):
        data = _get(
            f"{settings.RETURN_SERVICE_URL}/returns",
            token,
            {"page": page, "page_size": 100},
            "Return service",
        )
        rows = data["items"]
        for row in rows:
            created = datetime.fromisoformat(row["created_at"]).date()
            if date_from <= created <= date_to:
                found.append(row)
        if not rows or page * 100 >= data["total"]:
            break
        # newest first: once we pass the start date we can stop
        if datetime.fromisoformat(rows[-1]["created_at"]).date() < date_from:
            break
    return found


def fetch_low_stock(token: str) -> list:
    items = []
    for page in range(1, MAX_PAGES + 1):
        data = _get(
            f"{settings.INVENTORY_SERVICE_URL}/inventory",
            token,
            {"low_stock_only": "true", "page": page, "page_size": 100},
            "Inventory service",
        )
        items.extend(data["items"])
        if not data["items"] or len(items) >= data["total"]:
            break
    return items


def fetch_products(token: str) -> dict:
    """Product names and categories: {product_id: {'name': ..., 'category': ...}}."""
    products = {}
    for page in range(1, MAX_PAGES + 1):
        data = _get(
            f"{settings.PRODUCT_SERVICE_URL}/products",
            token,
            {"page": page, "page_size": 100},
            "Product service",
        )
        for p in data["items"]:
            products[p["id"]] = {"name": p["name"], "category": p["category"]}
        if not data["items"] or page * 100 >= data["total"]:
            break
    return products