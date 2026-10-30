import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response

from . import clients, exports, reports
from .dependencies import Actor, require_user

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("analytics")

app = FastAPI(title="Analytics and Reporting Service")

ReportName = Literal["sales", "orders", "inventory", "top-products"]
Granularity = Literal["day", "week", "month"]
SortBy = Literal["quantity", "revenue"]
MAX_RANGE_DAYS = 366


# ---------- helper functions ----------

def ensure_access(actor: Actor, name: str):
    allowed = ("administrator", "inventory_manager") if name == "inventory" else ("administrator",)
    if actor.role not in allowed:
        raise HTTPException(status_code=403, detail="You do not have permission to see this report")


def parse_range(date_from: Optional[date], date_to: Optional[date]):
    today = datetime.now(timezone.utc).date()
    end = date_to or today
    start = date_from or end - timedelta(days=29)  # default: the last 30 days
    if start > end:
        raise HTTPException(status_code=400, detail="date_from cannot be after date_to")
    if (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=400, detail=f"The date range can be at most {MAX_RANGE_DAYS} days"
        )
    return start, end


def build_report(name, actor, start, end, granularity, limit, sort_by):
    """Returns (json_data, report_for_download)."""
    token = actor.token
    if name == "sales":
        orders = clients.fetch_orders(token, start, end)
        returns = clients.fetch_returns(token, start, end)
        return reports.sales_report(orders, returns, start, end, granularity)
    if name == "orders":
        orders = clients.fetch_orders(token, start, end)
        returns = clients.fetch_returns(token, start, end)
        return reports.orders_report(orders, returns, start, end)
    if name == "inventory":
        items = clients.fetch_low_stock(token)
        products = clients.fetch_products(token)
        return reports.inventory_report(items, products, datetime.now(timezone.utc).date())
    orders = clients.fetch_orders(token, start, end)
    products = clients.fetch_products(token)
    return reports.top_products_report(orders, products, start, end, limit, sort_by)


# ---------- APIs ----------

@app.get("/health")
def health():
    return {"status": "ok", "service": "analytics"}


@app.get("/analytics/sales")
def sales(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    granularity: Granularity = "day",
    actor: Actor = Depends(require_user),
):
    ensure_access(actor, "sales")
    start, end = parse_range(date_from, date_to)
    data, _ = build_report("sales", actor, start, end, granularity, 10, "quantity")
    return data


@app.get("/analytics/orders")
def order_statistics(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    actor: Actor = Depends(require_user),
):
    ensure_access(actor, "orders")
    start, end = parse_range(date_from, date_to)
    data, _ = build_report("orders", actor, start, end, "day", 10, "quantity")
    return data


@app.get("/analytics/inventory")
def inventory_status(actor: Actor = Depends(require_user)):
    ensure_access(actor, "inventory")
    data, _ = build_report("inventory", actor, None, None, "day", 10, "quantity")
    return data


@app.get("/analytics/top-products")
def top_products(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = Query(10, ge=1, le=50),
    sort_by: SortBy = "quantity",
    actor: Actor = Depends(require_user),
):
    ensure_access(actor, "top-products")
    start, end = parse_range(date_from, date_to)
    data, _ = build_report("top-products", actor, start, end, "day", limit, sort_by)
    return data


@app.get("/analytics/export/{report}")
def export_report(
    report: ReportName,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    granularity: Granularity = "day",
    limit: int = Query(10, ge=1, le=50),
    sort_by: SortBy = "quantity",
    file_format: Literal["csv", "pdf"] = Query("csv", alias="format"),
    actor: Actor = Depends(require_user),
):
    ensure_access(actor, report)
    start, end = parse_range(date_from, date_to)
    _, built = build_report(report, actor, start, end, granularity, limit, sort_by)

    if file_format == "pdf":
        content, media_type = exports.to_pdf(built), "application/pdf"
    else:
        content, media_type = exports.to_csv(built), "text/csv"

    if report == "inventory":
        stamp = datetime.now(timezone.utc).date().isoformat()
    else:
        stamp = f"{start}_{end}"
    filename = f"{report}-{stamp}.{file_format}"
    logger.info(
        json.dumps(
            {"event": "report_downloaded", "user_id": actor.user_id, "report": report, "format": file_format}
        )
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )