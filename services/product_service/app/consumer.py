from services.common.consumer import EventConsumer
from services.common.redis_support import cache_bump

from .database import SessionLocal
from .models import Product, StockVersion


def handle_stock_event(envelope: dict) -> str:
    if envelope.get("type") != "inventory.stock_changed":
        return "ignored"
    data = envelope["data"]
    product_id = int(data["product_id"])
    quantity = max(0, int(data["quantity_available"]))
    version = int(data["version"])

    db = SessionLocal()
    try:
        row = db.get(StockVersion, product_id)
        if row is not None and row.version >= version:
            return "stale"  # an older event arrived late, so skip it
        if row is None:
            db.add(StockVersion(product_id=product_id, version=version))
        else:
            row.version = version
        product = db.get(Product, product_id)
        if product is not None:
            product.stock_quantity = quantity
        db.commit()
    finally:
        db.close()
    cache_bump("product")  # the catalog must show the new stock straight away
    return "updated"


def start_stock_consumer() -> EventConsumer:
    consumer = EventConsumer("product.stock", ["inventory.stock_changed"], handle_stock_event)
    consumer.start()
    return consumer