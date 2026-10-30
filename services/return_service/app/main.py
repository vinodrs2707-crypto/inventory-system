import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from . import clients, schemas
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .dependencies import Actor, require_staff, require_user
from .models import AuditLog, ReturnHistory, ReturnItem, ReturnRequest, utcnow

Base.metadata.create_all(bind=engine)
logger = logging.getLogger("returns")

# these returns still "use up" part of the quantity that can be returned
ACTIVE_STATUSES = ("requested", "approved", "received", "accepted", "refunded")
TRANSITIONS = {
    "requested": ("approved", "rejected"),
    "approved": ("received",),
    "received": ("accepted", "declined"),
}
ADMIN_ONLY = ("approved", "rejected")


# ---------- helper functions ----------

def add_audit(db: Session, user_id: Optional[int], action: str, detail: str = ""):
    db.add(AuditLog(user_id=user_id, action=action, detail=detail))


def add_history(db: Session, return_id: int, status: str, note: str, user_id: Optional[int]):
    db.add(ReturnHistory(return_id=return_id, status=status, note=note, changed_by=user_id))


def new_return_number() -> str:
    return f"RET-{utcnow():%Y%m%d}-{secrets.token_hex(3).upper()}"


def to_out(r: ReturnRequest) -> schemas.ReturnOut:
    return schemas.ReturnOut(
        id=r.id,
        return_number=r.return_number,
        order_id=r.order_id,
        user_id=r.user_id,
        status=r.status,
        refund_status=r.refund_status,
        refund_amount=r.refund_amount,
        refund_reference=r.refund_reference,
        items=[
            schemas.ReturnItemOut(
                order_item_id=i.order_item_id,
                product_id=i.product_id,
                product_name=i.product_name,
                quantity=i.quantity,
                unit_refund=i.unit_refund,
                reason=i.reason,
                comment=i.comment,
                accepted_quantity=i.accepted_quantity,
                restock=i.restock,
            )
            for i in r.items
        ],
        history=[
            schemas.HistoryOut(status=h.status, note=h.note, created_at=h.created_at)
            for h in r.history
        ],
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def to_summary(r: ReturnRequest) -> schemas.ReturnSummary:
    return schemas.ReturnSummary(
        id=r.id,
        return_number=r.return_number,
        order_id=r.order_id,
        status=r.status,
        refund_status=r.refund_status,
        refund_amount=r.refund_amount,
        item_count=sum(i.quantity for i in r.items),
        created_at=r.created_at,
    )


def already_requested(db: Session, order_id: int) -> dict:
    """How many of each order item are already in a return: {order_item_id: quantity}."""
    rows = (
        db.query(ReturnItem.order_item_id, func.sum(ReturnItem.quantity))
        .join(ReturnRequest, ReturnRequest.id == ReturnItem.return_id)
        .filter(ReturnRequest.order_id == order_id, ReturnRequest.status.in_(ACTIVE_STATUSES))
        .group_by(ReturnItem.order_item_id)
        .all()
    )
    return {item_id: int(total) for item_id, total in rows}


def load_return(db: Session, return_id: int, actor: Actor) -> ReturnRequest:
    """Other customers' returns look like they do not exist."""
    ret = db.get(ReturnRequest, return_id)
    allowed = ret is not None and (actor.role in ("administrator", "inventory_manager") or ret.user_id == actor.user_id)
    if not allowed:
        raise HTTPException(status_code=404, detail="Return not found")
    return ret


def process_refund(db: Session, ret: ReturnRequest):
    """Ask the Payment service to refund. Safe to call again and again."""
    if ret.status != "accepted" or ret.refund_status != "pending":
        return
    reference = f"{ret.return_number}-refund"
    result, why = clients.request_refund(
        ret.order_id, ret.refund_amount, reference, f"Return {ret.return_number}"
    )
    if result == "ok":
        ret.status = "refunded"
        ret.refund_status = "processed"
        ret.refund_reference = reference
        add_history(db, ret.id, "refunded", f"Refund of {ret.refund_amount:.2f} processed", None)
        add_audit(db, None, "return_refunded", ret.return_number)
    elif result == "rejected":
        ret.refund_status = "failed"
        add_history(db, ret.id, ret.status, f"Refund failed: {why}", None)
        add_audit(db, None, "return_refund_failed", f"{ret.return_number}: {why}")
    # 'unavailable': stay pending, the 1-minute job tries again
    db.commit()


# ---------- background job: retry refunds that could not be sent ----------

def run_refund_retry():
    db = SessionLocal()
    try:
        ids = [
            row.id
            for row in db.query(ReturnRequest.id)
            .filter(ReturnRequest.status == "accepted", ReturnRequest.refund_status == "pending")
            .all()
        ]
        for return_id in ids:
            ret = db.get(ReturnRequest, return_id)
            try:
                process_refund(db, ret)
            except Exception:
                db.rollback()
                logger.exception("Refund retry failed for return %s", return_id)
    finally:
        db.close()


async def refund_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(run_refund_retry)
        except Exception:
            logger.exception("Refund retry job failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(refund_loop())
    yield
    task.cancel()


app = FastAPI(title="Return and Refund Service", lifespan=lifespan)


# ---------- APIs ----------

@app.get("/health")
def health():
    return {"status": "ok", "service": "return"}


@app.post("/returns", response_model=schemas.ReturnOut, status_code=201)
def create_return(
    data: schemas.ReturnCreate,
    db: Session = Depends(get_db),
    user: Actor = Depends(require_user),
):
    info = clients.get_returnable(data.order_id, user.user_id)
    if not info["eligible"]:
        code = 404 if info["reason"] == "Order not found" else 409
        raise HTTPException(status_code=code, detail=info["reason"])

    delivered_at = datetime.fromisoformat(info["delivered_at"])
    if utcnow() > delivered_at + timedelta(days=settings.RETURN_WINDOW_DAYS):
        raise HTTPException(
            status_code=409,
            detail=f"The return period of {settings.RETURN_WINDOW_DAYS} days has ended",
        )

    by_item = {i["item_id"]: i for i in info["items"]}
    used = already_requested(db, data.order_id)
    lines = []
    for line in data.items:
        item = by_item.get(line.order_item_id)
        if item is None:
            raise HTTPException(
                status_code=400, detail=f"Item {line.order_item_id} cannot be returned from this order"
            )
        available = item["max_quantity"] - used.get(line.order_item_id, 0)
        if line.quantity > available:
            raise HTTPException(
                status_code=400,
                detail=f"Only {max(available, 0)} of '{item['product_name']}' can still be returned",
            )
        lines.append(
            ReturnItem(
                order_item_id=line.order_item_id,
                product_id=item["product_id"],
                product_name=item["product_name"],
                quantity=line.quantity,
                unit_refund=item["unit_refund"],
                reason=line.reason,
                comment=line.comment.strip() if line.comment else None,
            )
        )

    ret = ReturnRequest(
        return_number=new_return_number(),
        order_id=data.order_id,
        user_id=user.user_id,
        status="requested",
        refund_status="none",
    )
    ret.items = lines
    db.add(ret)
    db.flush()
    add_history(db, ret.id, "requested", "Return requested by customer", user.user_id)
    add_audit(db, user.user_id, "return_requested", ret.return_number)
    db.commit()
    db.refresh(ret)
    return to_out(ret)


@app.get("/returns", response_model=schemas.ReturnPage)
def list_all_returns(
    status: Optional[str] = Query(None, max_length=20),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff),
):
    query = db.query(ReturnRequest)
    if status:
        query = query.filter(ReturnRequest.status == status)
    total = query.count()
    rows = (
        query.order_by(ReturnRequest.created_at.desc(), ReturnRequest.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.ReturnPage(
        items=[to_summary(r) for r in rows], total=total, page=page, page_size=page_size
    )


# This one must stay ABOVE /returns/{return_id}
@app.get("/returns/my-returns", response_model=schemas.ReturnPage)
def my_returns(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: Actor = Depends(require_user),
):
    query = db.query(ReturnRequest).filter(ReturnRequest.user_id == user.user_id)
    total = query.count()
    rows = (
        query.order_by(ReturnRequest.created_at.desc(), ReturnRequest.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.ReturnPage(
        items=[to_summary(r) for r in rows], total=total, page=page, page_size=page_size
    )


@app.get("/returns/{return_id}", response_model=schemas.ReturnOut)
def get_return(
    return_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_user),
):
    return to_out(load_return(db, return_id, actor))


@app.patch("/returns/{return_id}/status", response_model=schemas.ReturnOut)
def update_return_status(
    return_id: int,
    data: schemas.StatusUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_staff),
):
    ret = db.get(ReturnRequest, return_id)
    if ret is None:
        raise HTTPException(status_code=404, detail="Return not found")
    if data.status not in TRANSITIONS.get(ret.status, ()):
        raise HTTPException(
            status_code=409,
            detail=f"A return that is {ret.status} cannot move to {data.status}",
        )
    if data.status in ADMIN_ONLY and actor.role != "administrator":
        raise HTTPException(status_code=403, detail="Only an administrator can approve or reject returns")

    claimed = db.execute(
        update(ReturnRequest)
        .where(ReturnRequest.id == ret.id, ReturnRequest.status == ret.status)
        .values(status=data.status, updated_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="The return was changed by someone else. Please refresh.")

    note = (data.note or "").strip() or f"Return {data.status}"

    if data.status == "accepted":
        by_item = {i.order_item_id: i for i in ret.items}
        for line in data.items:
            item = by_item.get(line.order_item_id)
            if item is None:
                db.rollback()
                raise HTTPException(status_code=400, detail=f"Item {line.order_item_id} is not part of this return")
            if line.accepted_quantity > item.quantity:
                db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail=f"Only {item.quantity} of '{item.product_name}' were requested",
                )
        accepted = {line.order_item_id: line for line in data.items}
        total_refund = 0.0
        restock_items = []
        for item in ret.items:
            line = accepted.get(item.order_item_id)
            quantity = line.accepted_quantity if line else 0
            item.accepted_quantity = quantity
            item.restock = bool(line.restock) if line and quantity > 0 else False
            total_refund += item.unit_refund * quantity
            if item.restock:
                restock_items.append({"product_id": item.product_id, "quantity": quantity})
        if total_refund <= 0:
            db.rollback()
            raise HTTPException(status_code=400, detail="No items were accepted. Use 'declined' instead.")
        try:
            # put resalable items back on the shelf BEFORE saving (safe to retry)
            if restock_items:
                clients.restock(f"{ret.return_number}-restock", restock_items, "Returned items accepted")
        except Exception:
            db.rollback()
            raise
        ret.refund_amount = round(total_refund, 2)
        ret.refund_status = "pending"

    add_history(db, ret.id, data.status, note, actor.user_id)
    add_audit(db, actor.user_id, "return_status_changed", f"{ret.return_number} -> {data.status}")
    db.commit()
    db.refresh(ret)

    if data.status == "accepted":
        process_refund(db, ret)
        db.refresh(ret)
    return to_out(ret)