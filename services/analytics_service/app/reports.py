from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Tuple

REVENUE_STATUSES = ("confirmed", "processing", "shipped", "delivered")
ALL_STATUSES = ("pending", "confirmed", "processing", "shipped", "delivered", "cancelled")


@dataclass
class Table:
    title: str
    columns: List[str]
    rows: List[list]


@dataclass
class Report:
    title: str
    subtitle: str
    summary: List[Tuple[str, str]]
    tables: List[Table]


def money(value) -> float:
    return round(float(value), 2)


def fmt(value) -> str:
    return f"{float(value):.2f}"


# ---------- periods (day, week, month) ----------

def period_of(dt: datetime, granularity: str) -> date:
    d = dt.date()
    if granularity == "week":
        return d - timedelta(days=d.weekday())  # the Monday of that week
    if granularity == "month":
        return d.replace(day=1)
    return d


def period_starts(date_from: date, date_to: date, granularity: str):
    current = period_of(datetime.combine(date_from, datetime.min.time()), granularity)
    while current <= date_to:
        yield current
        if granularity == "day":
            current += timedelta(days=1)
        elif granularity == "week":
            current += timedelta(days=7)
        else:
            current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)


def period_label(d: date, granularity: str) -> str:
    return f"{d:%Y-%m}" if granularity == "month" else d.isoformat()


# ---------- sales ----------

def sales_report(orders, returns, date_from, date_to, granularity):
    counted = [o for o in orders if o["status"] in REVENUE_STATUSES]
    gross = sum(o["total_amount"] for o in counted)
    discounts = sum(o["discount_amount"] for o in counted)
    tax = sum(o["tax_amount"] for o in counted)
    shipping = sum(o["shipping_amount"] for o in counted)
    cancellation_refunds = sum(o["refund_due"] for o in counted)
    return_refunds = sum(r["refund_amount"] for r in returns if r["refund_status"] == "processed")
    net = gross - cancellation_refunds - return_refunds
    average = gross / len(counted) if counted else 0.0

    buckets = {
        start: {"orders": 0, "revenue": 0.0}
        for start in period_starts(date_from, date_to, granularity)
    }
    for o in counted:
        key = period_of(datetime.fromisoformat(o["created_at"]), granularity)
        if key in buckets:
            buckets[key]["orders"] += 1
            buckets[key]["revenue"] += o["total_amount"]
    series = [
        {
            "period": period_label(start, granularity),
            "orders": b["orders"],
            "revenue": money(b["revenue"]),
            "average_order_value": money(b["revenue"] / b["orders"]) if b["orders"] else 0.0,
        }
        for start, b in buckets.items()
    ]

    totals = {
        "orders_counted": len(counted),
        "gross_revenue": money(gross),
        "discounts_given": money(discounts),
        "tax_collected": money(tax),
        "shipping_charged": money(shipping),
        "cancellation_refunds": money(cancellation_refunds),
        "return_refunds": money(return_refunds),
        "net_revenue": money(net),
        "average_order_value": money(average),
    }
    data = {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat(), "granularity": granularity},
        "totals": totals,
        "series": series,
    }
    report = Report(
        title="Sales report",
        subtitle=f"{date_from} to {date_to} (UTC), grouped by {granularity}",
        summary=[
            ("Orders counted", str(len(counted))),
            ("Gross revenue (INR)", fmt(gross)),
            ("Refunds for cancelled items (INR)", fmt(cancellation_refunds)),
            ("Refunds for returns (INR)", fmt(return_refunds)),
            ("Net revenue (INR)", fmt(net)),
            ("Average order value (INR)", fmt(average)),
            ("Discounts given (INR)", fmt(discounts)),
            ("Tax collected (INR)", fmt(tax)),
        ],
        tables=[
            Table(
                "Sales by period",
                ["Period", "Orders", "Revenue (INR)", "Average order value (INR)"],
                [[s["period"], s["orders"], fmt(s["revenue"]), fmt(s["average_order_value"])] for s in series],
            )
        ],
    )
    return data, report


# ---------- orders, cancellations and returns ----------

def orders_report(orders, returns, date_from, date_to):
    by_status = {s: 0 for s in ALL_STATUSES}
    for o in orders:
        by_status[o["status"]] = by_status.get(o["status"], 0) + 1
    total = len(orders)
    cancelled = by_status["cancelled"]
    cancel_rate = round(cancelled / total * 100, 2) if total else 0.0
    delivered = by_status["delivered"]

    return_by_status = {}
    for r in returns:
        return_by_status[r["status"]] = return_by_status.get(r["status"], 0) + 1
    return_requests = len(returns)
    return_rate = round(return_requests / delivered * 100, 2) if delivered else 0.0
    refunded = sum(r["refund_amount"] for r in returns if r["refund_status"] == "processed")

    data = {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "total_orders": total,
        "by_status": by_status,
        "cancellations": {"count": cancelled, "rate_percent": cancel_rate},
        "returns": {
            "requests": return_requests,
            "delivered_orders": delivered,
            "rate_percent": return_rate,
            "refunded_amount": money(refunded),
            "by_status": return_by_status,
        },
    }
    report = Report(
        title="Orders, cancellations and returns",
        subtitle=f"{date_from} to {date_to} (UTC)",
        summary=[
            ("Total orders", str(total)),
            ("Cancelled orders", str(cancelled)),
            ("Cancellation rate (%)", fmt(cancel_rate)),
            ("Delivered orders", str(delivered)),
            ("Return requests", str(return_requests)),
            ("Return rate (return requests per 100 delivered orders)", fmt(return_rate)),
            ("Refunded for returns (INR)", fmt(refunded)),
        ],
        tables=[
            Table(
                "Orders by status",
                ["Status", "Orders", "Share of orders (%)"],
                [[s, n, fmt(n / total * 100) if total else "0.00"] for s, n in by_status.items()],
            ),
            Table(
                "Returns by status",
                ["Status", "Return requests"],
                [[s, n] for s, n in sorted(return_by_status.items())],
            ),
        ],
    )
    return data, report


# ---------- inventory ----------

def inventory_report(items, products, today):
    def row(i):
        info = products.get(i["product_id"], {})
        return {
            "product_id": i["product_id"],
            "name": info.get("name", f"Product {i['product_id']} (not in catalog)"),
            "category": info.get("category", "Unknown"),
            "quantity_on_hand": i["quantity_on_hand"],
            "quantity_reserved": i["quantity_reserved"],
            "quantity_available": i["quantity_available"],
            "low_stock_threshold": i["low_stock_threshold"],
        }

    out = sorted((row(i) for i in items if i["out_of_stock"]), key=lambda r: r["product_id"])
    low = sorted(
        (row(i) for i in items if i["low_stock"] and not i["out_of_stock"]),
        key=lambda r: (r["quantity_available"], r["product_id"]),
    )
    columns = ["Product ID", "Product", "Category", "On hand", "Reserved", "Available", "Alert level"]

    def table_rows(rows):
        return [
            [r["product_id"], r["name"], r["category"], r["quantity_on_hand"],
             r["quantity_reserved"], r["quantity_available"], r["low_stock_threshold"]]
            for r in rows
        ]

    data = {
        "as_of": today.isoformat(),
        "counts": {"out_of_stock": len(out), "low_stock": len(low)},
        "out_of_stock": out,
        "low_stock": low,
    }
    report = Report(
        title="Low-stock and out-of-stock report",
        subtitle=f"Stock position on {today} (UTC)",
        summary=[("Out of stock products", str(len(out))), ("Low stock products", str(len(low)))],
        tables=[
            Table("Out of stock", columns, table_rows(out)),
            Table("Low stock", columns, table_rows(low)),
        ],
    )
    return data, report


# ---------- top products and categories ----------

def top_products_report(orders, products, date_from, date_to, limit, sort_by):
    stats = {}
    for o in orders:
        if o["status"] not in REVENUE_STATUSES:
            continue
        for item in o["items"]:
            kept = item["quantity"] - item["cancelled_quantity"]
            if kept <= 0:
                continue
            revenue = item["line_total"] * kept / item["quantity"]
            s = stats.setdefault(
                item["product_id"],
                {"product_id": item["product_id"], "name": item["product_name"], "quantity": 0, "revenue": 0.0},
            )
            s["quantity"] += kept
            s["revenue"] += revenue

    ranked = sorted(stats.values(), key=lambda s: (s[sort_by], s["quantity"]), reverse=True)
    top = []
    for rank, s in enumerate(ranked[:limit], start=1):
        top.append(
            {
                "rank": rank,
                "product_id": s["product_id"],
                "name": s["name"],
                "category": products.get(s["product_id"], {}).get("category", "Unknown"),
                "quantity_sold": s["quantity"],
                "revenue": money(s["revenue"]),
            }
        )

    category_totals = {}
    for s in stats.values():
        name = products.get(s["product_id"], {}).get("category", "Unknown")
        c = category_totals.setdefault(name, {"category": name, "quantity_sold": 0, "revenue": 0.0})
        c["quantity_sold"] += s["quantity"]
        c["revenue"] += s["revenue"]
    categories = sorted(
        category_totals.values(),
        key=lambda c: (c["quantity_sold"] if sort_by == "quantity" else c["revenue"]),
        reverse=True,
    )[:limit]
    categories = [
        {"rank": i, "category": c["category"], "quantity_sold": c["quantity_sold"], "revenue": money(c["revenue"])}
        for i, c in enumerate(categories, start=1)
    ]

    data = {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "sorted_by": sort_by,
        "products": top,
        "categories": categories,
    }
    report = Report(
        title="Top-selling products and categories",
        subtitle=f"{date_from} to {date_to} (UTC), sorted by {sort_by}. Revenue is before tax and discounts.",
        summary=[("Products sold", str(len(stats)))],
        tables=[
            Table(
                "Top products",
                ["Rank", "Product ID", "Product", "Category", "Quantity sold", "Revenue (INR)"],
                [[p["rank"], p["product_id"], p["name"], p["category"], p["quantity_sold"], fmt(p["revenue"])] for p in top],
            ),
            Table(
                "Top categories",
                ["Rank", "Category", "Quantity sold", "Revenue (INR)"],
                [[c["rank"], c["category"], c["quantity_sold"], fmt(c["revenue"])] for c in categories],
            ),
        ],
    )
    return data, report