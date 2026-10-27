import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import schemas
from .database import Base, SessionLocal, engine, get_db
from .dependencies import Actor, get_actor, require_staff, require_staff_or_internal
from .models import (
    InventoryItem,
    InventoryTransaction,
    Reservation,
    ReservationItem,
    utcnow,
)

Base.metadata.create_all(bind=engine)
logger = logging.getLogger("inventory")


# ---------- helper functions ----------

def to_out(item: InventoryItem) -> schemas.InventoryOut:
    available = item.quantity_on_hand - item.quantity_reserved
    return schemas.InventoryOut(
        product_id=item.product_id,
        quantity_on_hand=item.quantity_on_hand,
        quantity_reserved=item.quantity_reserved,
        quantity_available=available,
        low_stock_threshold=item.low_stock_threshold,
        low_stock=available <= item.low_stock_threshold,
        out_of_stock=available <= 0,
        updated_at=item.updated_at,
    )


def get_item(db: Session, product_id: int) -> InventoryItem:
    item = (
        db.query(InventoryItem)
        .populate_existing()
        .filter(InventoryItem.product_id == product_id)
        .first()
    )
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"No inventory record for product {product_id}",
        )
    return item


def apply_change(db: Session, product_id: int, on_hand_delta: int, reserved_delta: int) -> bool:
    """Change the stock in ONE atomic database step.

    The WHERE conditions make sure stock never goes negative and
    reserved never goes above on-hand. Two requests at the same time
    cannot oversell, because the database checks the rule while updating.
    """
    new_on_hand = InventoryItem.quantity_on_hand + on_hand_delta
    new_reserved = InventoryItem.quantity_reserved + reserved_delta
    result = db.execute(
        update(InventoryItem)
        .where(
            InventoryItem.product_id == product_id,
            new_on_hand >= 0,
            new_reserved >= 0,
            new_reserved <= new_on_hand,
        )
        .values(
            quantity_on_hand=new_on_hand,
            quantity_reserved=new_reserved,
            updated_at=utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def log_tx(
    db: Session,
    product_id: int,
    change_type: str,
    on_hand_change: int,
    reserved_change: int,
    reason: str,
    reference: Optional[str] = None,
    user_id: Optional[int] = None,
):
    item = get_item(db, product_id)
    db.add(
        InventoryTransaction(
            product_id=product_id,
            change_type=change_type,
            on_hand_change=on_hand_change,
            reserved_change=reserved_change,
            on_hand_after=item.quantity_on_hand,
            reserved_after=item.quantity_reserved,
            reason=reason,
            reference=reference,
            user_id=user_id,
        )
    )


def finish_reservation(
    db: Session,
    reservation: Reservation,
    new_status: str,
    reason: str,
    user_id: Optional[int],
    consume: bool,
) -> bool:
    """Close an active reservation. consume=True means the items were sold."""
    claimed = db.execute(
        update(Reservation)
        .where(Reservation.id == reservation.id, Reservation.status == "active")
        .values(status=new_status)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        return False  # another request already closed it

    for line in reservation.items:
        if consume:
            ok = apply_change(db, line.product_id, -line.quantity, -line.quantity)
            on_hand_change, change_type = -line.quantity, "sale"
        else:
            ok = apply_change(db, line.product_id, 0, -line.quantity)
            on_hand_change, change_type = 0, "release"
        if not ok:
            db.rollback()
            raise RuntimeError(f"Inventory out of sync for product {line.product_id}")
        log_tx(
            db,
            line.product_id,
            change_type,
            on_hand_change,
            -line.quantity,
            reason,
            reservation.reference,
            user_id,
        )
    db.commit()
    return True


def expire_old_reservations(db: Session) -> int:
    ids = [
        r.id
        for r in db.query(Reservation.id)
        .filter(Reservation.status == "active", Reservation.expires_at < utcnow())
        .all()
    ]
    count = 0
    for reservation_id in ids:
        reservation = db.get(Reservation, reservation_id)
        if reservation and finish_reservation(
            db, reservation, "expired", "Reservation expired", None, consume=False
        ):
            count += 1
    return count


def get_reservation_or_404(db: Session, reservation_id: int) -> Reservation:
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    db.refresh(reservation)
    return reservation


# ---------- background job: expire old reservations every 30 seconds ----------

def run_expiry():
    db = SessionLocal()
    try:
        count = expire_old_reservations(db)
        if count:
            logger.info("Expired %s reservation(s)", count)
    finally:
        db.close()


async def expiry_loop():
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.to_thread(run_expiry)
        except Exception:
            logger.exception("Reservation expiry job failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(expiry_loop())
    yield
    task.cancel()


app = FastAPI(title="Inventory Service", lifespan=lifespan)


# ---------- APIs ----------

@app.get("/health")
def health():
    return {"status": "ok", "service": "inventory"}


@app.post("/inventory", response_model=schemas.InventoryOut, status_code=201)
def create_inventory(
    data: schemas.InventoryCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff),
):
    item = InventoryItem(
        product_id=data.product_id,
        quantity_on_hand=data.quantity,
        quantity_reserved=0,
        low_stock_threshold=data.low_stock_threshold,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="This product already has an inventory record"
        )
    log_tx(db, data.product_id, "addition", data.quantity, 0, "Initial stock", None, actor.user_id)
    db.commit()
    return to_out(get_item(db, data.product_id))


@app.get("/inventory", response_model=schemas.InventoryPage)
def list_inventory(
    low_stock_only: bool = False,
    out_of_stock_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff),
):
    available = InventoryItem.quantity_on_hand - InventoryItem.quantity_reserved
    query = db.query(InventoryItem)
    if low_stock_only:
        query = query.filter(available <= InventoryItem.low_stock_threshold)
    if out_of_stock_only:
        query = query.filter(available <= 0)
    total = query.count()
    items = (
        query.order_by(InventoryItem.product_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.InventoryPage(
        items=[to_out(i) for i in items], total=total, page=page, page_size=page_size
    )


@app.get("/inventory/reports/movements", response_model=schemas.TransactionPage)
def movement_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    product_id: Optional[int] = Query(None, ge=1),
    change_type: Optional[str] = Query(None, max_length=30),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from cannot be after date_to")
    query = db.query(InventoryTransaction)
    if date_from:
        query = query.filter(InventoryTransaction.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.filter(InventoryTransaction.created_at <= datetime.combine(date_to, time.max))
    if product_id:
        query = query.filter(InventoryTransaction.product_id == product_id)
    if change_type:
        query = query.filter(InventoryTransaction.change_type == change_type)
    total = query.count()
    rows = (
        query.order_by(InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.TransactionPage(items=rows, total=total, page=page, page_size=page_size)


# ----- reservations -----

@app.post("/inventory/reservations", response_model=schemas.ReservationOut, status_code=201)
def create_reservation(
    data: schemas.ReservationCreate,
    response: Response,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff_or_internal),
):
    expire_old_reservations(db)  # free up stock from old reservations first

    # Same reference sent twice = same reservation (no double reserving)
    existing = db.query(Reservation).filter(Reservation.reference == data.reference).first()
    if existing:
        if existing.status == "active":
            response.status_code = 200
            return existing
        raise HTTPException(
            status_code=409,
            detail=f"This reference was already used (status: {existing.status})",
        )

    lines = sorted(data.items, key=lambda i: i.product_id)
    for line in lines:
        if not apply_change(db, line.product_id, 0, line.quantity):
            exists = db.query(InventoryItem.id).filter(
                InventoryItem.product_id == line.product_id
            ).first()
            db.rollback()  # undo any lines already reserved
            if not exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"No inventory record for product {line.product_id}",
                )
            raise HTTPException(
                status_code=409,
                detail=f"Not enough stock for product {line.product_id}",
            )

    reservation = Reservation(
        reference=data.reference,
        status="active",
        expires_at=utcnow() + timedelta(minutes=data.ttl_minutes),
        user_id=actor.user_id,
    )
    reservation.items = [
        ReservationItem(product_id=l.product_id, quantity=l.quantity) for l in lines
    ]
    db.add(reservation)
    for line in lines:
        log_tx(
            db,
            line.product_id,
            "reservation",
            0,
            line.quantity,
            f"Reserved for {data.reference}",
            data.reference,
            actor.user_id,
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Reservation).filter(Reservation.reference == data.reference).first()
        if existing and existing.status == "active":
            response.status_code = 200
            return existing
        raise HTTPException(status_code=409, detail="Duplicate reservation reference")
    db.refresh(reservation)
    return reservation


@app.get("/inventory/reservations/{reservation_id}", response_model=schemas.ReservationOut)
def get_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff_or_internal),
):
    return get_reservation_or_404(db, reservation_id)


@app.post(
    "/inventory/reservations/{reservation_id}/release",
    response_model=schemas.ReservationOut,
)
def release_reservation(
    reservation_id: int,
    data: Optional[schemas.ReleaseRequest] = None,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff_or_internal),
):
    reservation = get_reservation_or_404(db, reservation_id)
    if reservation.status in ("released", "expired"):
        return reservation  # already done, safe to call again
    if reservation.status == "confirmed":
        raise HTTPException(status_code=409, detail="Stock was already sold for this reservation")
    reason = data.reason if data else "Reservation released"
    finish_reservation(db, reservation, "released", reason, actor.user_id, consume=False)
    return get_reservation_or_404(db, reservation_id)


@app.post(
    "/inventory/reservations/{reservation_id}/confirm",
    response_model=schemas.ReservationOut,
)
def confirm_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff_or_internal),
):
    """Called after payment succeeds: reserved stock becomes a real sale."""
    reservation = get_reservation_or_404(db, reservation_id)
    if reservation.status == "confirmed":
        return reservation  # already done, safe to call again
    if reservation.status in ("released", "expired"):
        raise HTTPException(status_code=409, detail=f"Reservation is {reservation.status}")
    if reservation.expires_at < utcnow():
        finish_reservation(db, reservation, "expired", "Reservation expired", None, consume=False)
        raise HTTPException(status_code=409, detail="Reservation has expired")
    finish_reservation(
        db, reservation, "confirmed", f"Sold - {reservation.reference}", actor.user_id, consume=True
    )
    return get_reservation_or_404(db, reservation_id)


# ----- single product stock -----

@app.get("/inventory/{product_id}", response_model=schemas.InventoryOut)
def get_inventory(
    product_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    return to_out(get_item(db, product_id))


@app.patch("/inventory/{product_id}/stock", response_model=schemas.InventoryOut)
def update_stock(
    product_id: int,
    data: schemas.StockUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff),
):
    item = get_item(db, product_id)
    if data.action == "add":
        delta, change_type = data.quantity, "addition"
    elif data.action == "deduct":
        delta, change_type = -data.quantity, "deduction"
    else:
        delta, change_type = data.quantity - item.quantity_on_hand, "adjustment"

    if not apply_change(db, product_id, delta, 0):
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Not enough free stock for this change. Stock reserved for orders cannot be removed.",
        )
    log_tx(db, product_id, change_type, delta, 0, data.reason.strip(), None, actor.user_id)
    db.commit()
    return to_out(get_item(db, product_id))


@app.patch("/inventory/{product_id}/threshold", response_model=schemas.InventoryOut)
def update_threshold(
    product_id: int,
    data: schemas.ThresholdUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff),
):
    item = get_item(db, product_id)
    item.low_stock_threshold = data.low_stock_threshold
    db.commit()
    return to_out(get_item(db, product_id))


@app.get("/inventory/{product_id}/transactions", response_model=schemas.TransactionPage)
def product_transactions(
    product_id: int,
    change_type: Optional[str] = Query(None, max_length=30),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff),
):
    get_item(db, product_id)  # 404 if the product has no inventory record
    query = db.query(InventoryTransaction).filter(InventoryTransaction.product_id == product_id)
    if change_type:
        query = query.filter(InventoryTransaction.change_type == change_type)
    total = query.count()
    rows = (
        query.order_by(InventoryTransaction.created_at.desc(), InventoryTransaction.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.TransactionPage(items=rows, total=total, page=page, page_size=page_size)


@app.post("/inventory/restock")
def restock(
    data: schemas.RestockRequest,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff_or_internal),
):
    """Put sold stock back (for example when a paid order is cancelled)."""
    already = (
        db.query(InventoryTransaction.id)
        .filter(
            InventoryTransaction.change_type == "restock",
            InventoryTransaction.reference == data.reference,
        )
        .first()
    )
    if already:
        return {"restocked": False, "message": "Stock was already restored for this reference"}

    for line in sorted(data.items, key=lambda i: i.product_id):
        if not apply_change(db, line.product_id, line.quantity, 0):
            exists = db.query(InventoryItem.id).filter(
                InventoryItem.product_id == line.product_id
            ).first()
            db.rollback()
            if not exists:
                raise HTTPException(
                    status_code=404,
                    detail=f"No inventory record for product {line.product_id}",
                )
            raise HTTPException(status_code=409, detail="Could not restore stock")
        log_tx(
            db,
            line.product_id,
            "restock",
            line.quantity,
            0,
            data.reason,
            data.reference,
            actor.user_id,
        )
    db.commit()
    return {"restocked": True, "message": "Stock restored"}