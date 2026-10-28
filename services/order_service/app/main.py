import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import clients, schemas
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .dependencies import (
    STAFF_ROLES,
    Actor,
    get_actor,
    require_internal,
    require_staff,
    require_user,
)
from .models import (
    AuditLog,
    IdempotencyKey,
    Order,
    OrderItem,
    OrderItemCancellation,
    OrderStatusHistory,
    utcnow,
)

Base.metadata.create_all(bind=engine)
logger = logging.getLogger("orders")

CANCELLABLE = ("pending", "confirmed", "processing")
ITEM_CANCELLABLE = ("confirmed", "processing")
# the only allowed forward moves for staff: current status -> next status
NEXT_STATUS = {"confirmed": "processing", "processing": "shipped", "shipped": "delivered"}


# ---------- helper functions ----------

def add_audit(db: Session, user_id: Optional[int], action: str, detail: str = ""):
    db.add(AuditLog(user_id=user_id, action=action, detail=detail))


def add_history(db: Session, order_id: int, status: str, note: str, user_id: Optional[int]):
    db.add(
        OrderStatusHistory(order_id=order_id, status=status, note=note, changed_by=user_id)
    )


def new_order_number() -> str:
    return f"ORD-{utcnow():%Y%m%d}-{secrets.token_hex(3).upper()}"


def cancelled_map(o: Order) -> dict:
    """How many of each item were already cancelled: {item_id: quantity}."""
    done = {}
    for c in o.cancellations:
        done[c.order_item_id] = done.get(c.order_item_id, 0) + c.quantity
    return done


def to_summary(o: Order) -> schemas.OrderSummary:
    return schemas.OrderSummary(
        id=o.id,
        order_number=o.order_number,
        status=o.status,
        payment_status=o.payment_status,
        total_amount=o.total_amount,
        item_count=sum(i.quantity for i in o.items),
        created_at=o.created_at,
    )


def to_detail(o: Order) -> schemas.OrderDetail:
    done = cancelled_map(o)
    return schemas.OrderDetail(
        id=o.id,
        order_number=o.order_number,
        user_id=o.user_id,
        status=o.status,
        payment_status=o.payment_status,
        items=[
            schemas.OrderItemOut(
                id=i.id,
                product_id=i.product_id,
                product_name=i.product_name,
                unit_price=i.unit_price,
                quantity=i.quantity,
                line_total=i.line_total,
                cancelled_quantity=done.get(i.id, 0),
            )
            for i in o.items
        ],
        subtotal=o.subtotal,
        discount_amount=o.discount_amount,
        coupon_code=o.coupon_code,
        tax_amount=o.tax_amount,
        shipping_amount=o.shipping_amount,
        total_amount=o.total_amount,
        refund_due=round(sum(c.refund_amount for c in o.cancellations), 2),
        shipping=schemas.ShippingOut(
            full_name=o.shipping_name,
            phone=o.shipping_phone,
            address_line=o.shipping_address,
            city=o.shipping_city,
            state=o.shipping_state,
            postal_code=o.shipping_postal_code,
        ),
        history=[
            schemas.HistoryOut(status=h.status, note=h.note, created_at=h.created_at)
            for h in o.history
        ],
        can_cancel=o.status in CANCELLABLE,
        cancel_reason=o.cancel_reason,
        created_at=o.created_at,
        updated_at=o.updated_at,
    )


def load_order(db: Session, order_id: int, actor: Actor) -> Order:
    """Find an order. Other customers' orders look like they do not exist."""
    order = db.get(Order, order_id)
    allowed = order is not None and (
        actor.role in STAFF_ROLES
        or actor.role == "internal"
        or order.user_id == actor.user_id
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def do_cancel(db: Session, order: Order, reason: str, user_id: Optional[int]) -> Order:
    if order.status == "cancelled":
        return order  # already done, safe to call again
    if order.status not in CANCELLABLE:
        raise HTTPException(
            status_code=409, detail=f"An order that is {order.status} cannot be cancelled"
        )
    old_status = order.status
    payment_status = "refund_pending" if order.payment_status == "paid" else order.payment_status

    claimed = db.execute(
        update(Order)
        .where(Order.id == order.id, Order.status == old_status)
        .values(
            status="cancelled",
            cancel_reason=reason,
            payment_status=payment_status,
            updated_at=utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The order was changed by someone else. Please refresh and try again.",
        )
    add_history(db, order.id, "cancelled", reason, user_id)
    add_audit(db, user_id, "order_cancelled", f"{order.order_number}: {reason}")

    # Give back stock and coupon BEFORE saving. If one of these fails,
    # nothing is saved and the cancel can safely be tried again.
    try:
        if old_status == "pending":
            if order.reservation_id:
                clients.release_reservation(order.reservation_id, "Order cancelled")
        else:
            # only the items that were not already cancelled one by one
            done = cancelled_map(order)
            items = [
                {"product_id": i.product_id, "quantity": i.quantity - done.get(i.id, 0)}
                for i in order.items
                if i.quantity - done.get(i.id, 0) > 0
            ]
            if items:
                clients.restock(f"{order.order_number}-cancel", items, "Order cancelled")
        if order.coupon_code:
            clients.release_coupon(order.order_number)
    except Exception:
        db.rollback()
        raise
    db.commit()
    db.refresh(order)
    return order


# ---------- background job: cancel orders that were never paid ----------

def run_expiry():
    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(minutes=settings.PENDING_ORDER_MINUTES)
        ids = [
            row.id
            for row in db.query(Order.id)
            .filter(Order.status == "pending", Order.created_at < cutoff)
            .all()
        ]
        for order_id in ids:
            order = db.get(Order, order_id)
            try:
                do_cancel(db, order, "Payment was not completed in time", None)
                logger.info("Cancelled unpaid order %s", order.order_number)
            except Exception:
                db.rollback()
                logger.exception("Could not cancel unpaid order %s", order_id)
    finally:
        db.close()


async def expiry_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(run_expiry)
        except Exception:
            logger.exception("Order expiry job failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(expiry_loop())
    yield
    task.cancel()


app = FastAPI(title="Order Management Service", lifespan=lifespan)


# ---------- APIs ----------

@app.get("/health")
def health():
    return {"status": "ok", "service": "order"}


@app.post("/orders", response_model=schemas.OrderDetail, status_code=201)
def create_order(
    data: schemas.OrderCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: Actor = Depends(require_user),
    idempotency_key: str = Header(min_length=8, max_length=100),
):
    # Step 1: idempotency. The same key from the same user gives the same order.
    record = IdempotencyKey(user_id=user.user_id, key=idempotency_key)
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(IdempotencyKey)
            .filter(IdempotencyKey.user_id == user.user_id, IdempotencyKey.key == idempotency_key)
            .first()
        )
        if existing and existing.order_id:
            response.status_code = 200
            return to_detail(db.get(Order, existing.order_id))
        raise HTTPException(status_code=409, detail="This request is already being processed")
    key_id = record.id

    reservation = None
    redeemed = False
    order_number = new_order_number()
    try:
        # Step 2: check the cart (live prices and stock)
        cart = clients.get_valid_cart(user.token)

        # Step 3: hold the stock
        lines = [
            {"product_id": i["product_id"], "quantity": i["quantity"]} for i in cart["items"]
        ]
        reservation = clients.reserve_stock(order_number, lines, settings.PENDING_ORDER_MINUTES)

        # Step 4: use the coupon (the Coupon service checks every rule)
        discount = 0.0
        coupon_code = None
        if data.coupon_code:
            result = clients.redeem_coupon(
                data.coupon_code, order_number, cart["subtotal"], user.user_id
            )
            discount = result["discount_amount"]
            coupon_code = result["code"]
            redeemed = True

        # Step 5: work out the money
        subtotal = cart["subtotal"]
        taxable = round(subtotal - discount, 2)
        tax = round(taxable * settings.TAX_RATE, 2)
        shipping = 0.0 if taxable >= settings.FREE_SHIPPING_THRESHOLD else settings.SHIPPING_FEE
        total = round(taxable + tax + shipping, 2)

        # Step 6: save the order
        ship = data.shipping
        order = Order(
            order_number=order_number,
            user_id=user.user_id,
            status="pending",
            payment_status="pending",
            subtotal=subtotal,
            discount_amount=discount,
            coupon_code=coupon_code,
            tax_amount=tax,
            shipping_amount=shipping,
            total_amount=total,
            reservation_id=reservation["id"],
            shipping_name=ship.full_name.strip(),
            shipping_phone=ship.phone,
            shipping_address=ship.address_line.strip(),
            shipping_city=ship.city.strip(),
            shipping_state=ship.state.strip(),
            shipping_postal_code=ship.postal_code.strip(),
        )
        order.items = [
            OrderItem(
                product_id=i["product_id"],
                product_name=i["name"],
                unit_price=i["unit_price"],
                quantity=i["quantity"],
                line_total=i["line_total"],
            )
            for i in cart["items"]
        ]
        db.add(order)
        db.flush()
        add_history(db, order.id, "pending", "Order placed. Waiting for payment.", user.user_id)
        add_audit(db, user.user_id, "order_created", order_number)
        db.get(IdempotencyKey, key_id).order_id = order.id
        db.commit()
    except Exception:
        # Undo everything we did, so no stock or coupon stays stuck
        db.rollback()
        if redeemed:
            clients.quietly(clients.release_coupon, order_number)
        if reservation:
            clients.quietly(
                clients.release_reservation, reservation["id"], "Order could not be created"
            )
        db.query(IdempotencyKey).filter(IdempotencyKey.id == key_id).delete()
        db.commit()
        raise

    clients.quietly(clients.clear_cart, user.token)
    db.refresh(order)
    return to_detail(order)


@app.get("/orders", response_model=schemas.OrderPage)
def list_all_orders(
    status: Optional[str] = Query(None, max_length=20),
    user_id: Optional[int] = Query(None, ge=1),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from cannot be after date_to")
    query = db.query(Order)
    if status:
        query = query.filter(Order.status == status)
    if user_id:
        query = query.filter(Order.user_id == user_id)
    if date_from:
        query = query.filter(Order.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.filter(Order.created_at <= datetime.combine(date_to, time.max))
    total = query.count()
    rows = (
        query.order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.OrderPage(
        items=[to_summary(o) for o in rows], total=total, page=page, page_size=page_size
    )


# This one must stay ABOVE /orders/{order_id}
@app.get("/orders/my-orders", response_model=schemas.OrderPage)
def my_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: Actor = Depends(require_user),
):
    query = db.query(Order).filter(Order.user_id == user.user_id)
    total = query.count()
    rows = (
        query.order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.OrderPage(
        items=[to_summary(o) for o in rows], total=total, page=page, page_size=page_size
    )


@app.get("/orders/{order_id}", response_model=schemas.OrderDetail)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    return to_detail(load_order(db, order_id, actor))


@app.patch("/orders/{order_id}/status", response_model=schemas.OrderDetail)
def update_status(
    order_id: int,
    data: schemas.StatusUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff),
):
    order = load_order(db, order_id, actor)
    if NEXT_STATUS.get(order.status) != data.status:
        raise HTTPException(
            status_code=409,
            detail=f"An order that is {order.status} cannot move to {data.status}",
        )
    claimed = db.execute(
        update(Order)
        .where(Order.id == order.id, Order.status == order.status)
        .values(status=data.status, updated_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="The order was changed by someone else. Please refresh."
        )
    add_history(db, order.id, data.status, data.note or f"Order {data.status}", actor.user_id)
    add_audit(db, actor.user_id, "order_status_changed", f"{order.order_number} -> {data.status}")
    db.commit()
    db.refresh(order)
    return to_detail(order)


@app.post("/orders/{order_id}/cancel", response_model=schemas.OrderDetail)
def cancel_order(
    order_id: int,
    data: Optional[schemas.CancelRequest] = None,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_user),
):
    order = load_order(db, order_id, actor)
    if actor.role == "inventory_manager":
        raise HTTPException(status_code=403, detail="You do not have permission to do this")
    reason = data.reason if data else "Cancelled by customer"
    order = do_cancel(db, order, reason, actor.user_id)
    return to_detail(order)


@app.post("/orders/{order_id}/cancel-items", response_model=schemas.OrderDetail)
def cancel_items(
    order_id: int,
    data: schemas.CancelItemsRequest,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_user),
):
    order = load_order(db, order_id, actor)
    if actor.role == "inventory_manager":
        raise HTTPException(status_code=403, detail="You do not have permission to do this")
    if order.status not in ITEM_CANCELLABLE:
        raise HTTPException(
            status_code=409,
            detail="Items can only be cancelled while the order is confirmed or processing. "
            "To stop a pending order, cancel the whole order.",
        )

    by_id = {i.id: i for i in order.items}
    done = cancelled_map(order)
    requested = {}
    for line in data.items:
        item = by_id.get(line.item_id)
        if item is None:
            raise HTTPException(
                status_code=400, detail=f"Item {line.item_id} is not part of this order"
            )
        remaining = item.quantity - done.get(item.id, 0)
        if line.quantity > remaining:
            raise HTTPException(
                status_code=400,
                detail=f"Only {remaining} of '{item.product_name}' can still be cancelled",
            )
        requested[item.id] = line.quantity

    # If nothing would be left, this is really a full cancellation
    left = sum(i.quantity - done.get(i.id, 0) - requested.get(i.id, 0) for i in order.items)
    if left == 0:
        return to_detail(do_cancel(db, order, data.reason, actor.user_id))

    # Refund = item price, minus its share of the coupon discount, plus tax
    discount_ratio = order.discount_amount / order.subtotal if order.subtotal > 0 else 0
    taxable = order.subtotal - order.discount_amount
    tax_rate = order.tax_amount / taxable if taxable > 0 else 0
    batch = max((c.batch_number for c in order.cancellations), default=0) + 1

    restock_items = []
    total_refund = 0.0
    for line in data.items:
        item = by_id[line.item_id]
        net = round(item.unit_price * line.quantity * (1 - discount_ratio), 2)
        refund = round(net + net * tax_rate, 2)
        total_refund += refund
        db.add(
            OrderItemCancellation(
                order_id=order.id,
                order_item_id=item.id,
                batch_number=batch,
                quantity=line.quantity,
                refund_amount=refund,
                reason=data.reason,
                cancelled_by=actor.user_id,
            )
        )
        restock_items.append({"product_id": item.product_id, "quantity": line.quantity})

    count = sum(requested.values())
    add_history(
        db,
        order.id,
        order.status,
        f"{count} item(s) cancelled. Refund due: {total_refund:.2f}",
        actor.user_id,
    )
    add_audit(db, actor.user_id, "order_items_cancelled", f"{order.order_number}: {count} item(s)")

    try:
        db.flush()  # a duplicate request at the same moment fails here
        clients.restock(f"{order.order_number}-partial-{batch}", restock_items, "Items cancelled")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Please try again")
    except Exception:
        db.rollback()
        raise
    db.refresh(order)
    return to_detail(order)


@app.post("/orders/{order_id}/payment-result", response_model=schemas.OrderDetail)
def payment_result(
    order_id: int,
    data: schemas.PaymentResult,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_internal),
):
    """Called by the Payment service when a payment finishes."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if data.status == "succeeded":
        if order.payment_status == "paid":
            return to_detail(order)  # already done, safe to call again
        if order.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"The order is {order.status}, so this payment cannot confirm it",
            )
        clients.confirm_reservation(order.reservation_id)  # reserved stock becomes sold
        claimed = db.execute(
            update(Order)
            .where(Order.id == order.id, Order.status == "pending")
            .values(
                status="confirmed",
                payment_status="paid",
                payment_id=data.payment_id,
                updated_at=utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="The order was changed. Please retry.")
        add_history(db, order.id, "confirmed", "Payment received. Order confirmed.", None)
        add_audit(db, None, "payment_succeeded", f"{order.order_number} / {data.payment_id}")
        db.commit()
    else:
        if order.status != "pending":
            return to_detail(order)  # nothing left to do
        order.payment_status = "failed"
        order.payment_id = data.payment_id
        add_history(db, order.id, "pending", "Payment failed. You can try again.", None)
        add_audit(db, None, "payment_failed", f"{order.order_number} / {data.payment_id}")
        db.commit()

    db.refresh(order)
    return to_detail(order)