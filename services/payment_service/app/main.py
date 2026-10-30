import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import clients, schemas
from .database import Base, SessionLocal, engine, get_db
from .dependencies import Actor, require_user
from .models import AuditLog, IdempotencyKey, Payment, utcnow

Base.metadata.create_all(bind=engine)
logger = logging.getLogger("payments")

OUTCOMES = {"success": "succeeded", "failure": "failed", "pending": "pending"}


# ---------- helper functions ----------

def add_audit(db: Session, user_id: Optional[int], action: str, detail: str = ""):
    db.add(AuditLog(user_id=user_id, action=action, detail=detail))


def new_reference() -> str:
    return f"PAY-{secrets.token_hex(5).upper()}"


def to_out(p: Payment) -> schemas.PaymentOut:
    return schemas.PaymentOut(
        id=p.id,
        reference=p.reference,
        order_id=p.order_id,
        amount=p.amount,
        currency=p.currency,
        method=p.method,
        status=p.status,
        order_synced=p.order_synced,
        failure_reason=p.failure_reason,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def load_payment(db: Session, payment_id: int, actor: Actor) -> Payment:
    """Other customers' payments look like they do not exist."""
    payment = db.get(Payment, payment_id)
    allowed = payment is not None and (
        actor.role == "administrator" or payment.user_id == actor.user_id
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


def sync_with_order(db: Session, payment: Payment):
    """Tell the Order service how the payment ended."""
    outcome = "succeeded" if payment.status == "succeeded" else "failed"
    result = clients.send_payment_result(payment.order_id, payment.reference, outcome)
    if result == "ok":
        payment.order_synced = True
    elif result == "rejected":
        if outcome == "succeeded":
            # Money was taken but the order cannot be confirmed (for example it
            # was cancelled meanwhile). The money has to be given back.
            payment.status = "refund_pending"
            payment.failure_reason = "Order could not be confirmed"
            add_audit(db, payment.user_id, "payment_needs_refund", payment.reference)
        payment.order_synced = True
    # "unavailable": leave order_synced False; the background job tries again
    db.commit()


# ---------- background job: retry telling the Order service ----------

def run_resync():
    db = SessionLocal()
    try:
        rows = (
            db.query(Payment)
            .filter(Payment.order_synced == False, Payment.status.in_(("succeeded", "failed")))  # noqa: E712
            .all()
        )
        for payment in rows:
            try:
                sync_with_order(db, payment)
            except Exception:
                db.rollback()
                logger.exception("Could not sync payment %s", payment.reference)
    finally:
        db.close()


async def resync_loop():
    while True:
        await asyncio.sleep(30)
        try:
            await asyncio.to_thread(run_resync)
        except Exception:
            logger.exception("Payment resync job failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(resync_loop())
    yield
    task.cancel()


app = FastAPI(title="Payment Service", lifespan=lifespan)


# ---------- APIs ----------

@app.get("/health")
def health():
    return {"status": "ok", "service": "payment"}


@app.post("/payments", response_model=schemas.PaymentOut, status_code=201)
def create_payment(
    data: schemas.PaymentCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: Actor = Depends(require_user),
    idempotency_key: str = Header(min_length=8, max_length=100),
):
    # Same key from the same user = same payment (no double charge)
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
        if existing and existing.payment_id:
            response.status_code = 200
            return to_out(db.get(Payment, existing.payment_id))
        raise HTTPException(status_code=409, detail="This request is already being processed")
    key_id = record.id

    try:
        # The amount always comes from the Order service, never from the customer
        order = clients.get_order(data.order_id)
        if order["user_id"] != user.user_id:
            raise HTTPException(status_code=404, detail="Order not found")
        if order["status"] != "pending" or order["payment_status"] == "paid":
            raise HTTPException(
                status_code=409, detail=f"This order is {order['status']} and cannot be paid"
            )
        active = (
            db.query(Payment.id)
            .filter(
                Payment.order_id == data.order_id,
                Payment.status.in_(("pending", "succeeded", "refund_pending")),
            )
            .first()
        )
        if active:
            raise HTTPException(
                status_code=409,
                detail="A payment for this order is already in progress or completed",
            )

        status = OUTCOMES[data.simulate]
        payment = Payment(
            reference=new_reference(),
            order_id=data.order_id,
            user_id=user.user_id,
            amount=order["total_amount"],
            method=data.method,
            status=status,
            order_synced=(status == "pending"),
            failure_reason="Payment declined (simulated)" if status == "failed" else None,
        )
        db.add(payment)
        db.flush()
        add_audit(db, user.user_id, "payment_created", f"{payment.reference} {status}")
        db.get(IdempotencyKey, key_id).payment_id = payment.id
        db.commit()
    except Exception:
        db.rollback()
        db.query(IdempotencyKey).filter(IdempotencyKey.id == key_id).delete()
        db.commit()
        raise

    if payment.status in ("succeeded", "failed"):
        sync_with_order(db, payment)
    db.refresh(payment)
    return to_out(payment)


@app.get("/payments/{payment_id}", response_model=schemas.PaymentOut)
def get_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_user),
):
    return to_out(load_payment(db, payment_id, actor))


@app.post("/payments/{payment_id}/cancel", response_model=schemas.PaymentOut)
def cancel_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_user),
):
    payment = load_payment(db, payment_id, actor)
    if payment.status == "cancelled":
        return to_out(payment)  # already done, safe to call again
    if payment.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"A payment that is {payment.status} cannot be cancelled. "
            "To get your money back, cancel the order instead.",
        )
    claimed = db.execute(
        update(Payment)
        .where(Payment.id == payment.id, Payment.status == "pending")
        .values(status="cancelled", updated_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="The payment was changed meanwhile. Please refresh."
        )
    add_audit(db, actor.user_id, "payment_cancelled", payment.reference)
    db.commit()
    db.refresh(payment)
    return to_out(payment)


# ----- refunds (called by the Return service) -----
from pydantic import BaseModel, Field
from sqlalchemy import func

from .dependencies import get_actor
from .models import Refund


class RefundRequest(BaseModel):
    order_id: int = Field(ge=1)
    amount: float = Field(gt=0, le=100_000_000)
    reference: str = Field(min_length=3, max_length=100)
    reason: str = Field(min_length=3, max_length=255)


def refund_out(refund: Refund) -> dict:
    return {
        "refund_id": refund.id,
        "reference": refund.reference,
        "status": refund.status,
        "amount": refund.amount,
    }


@app.post("/payments/refunds")
def create_refund(
    data: RefundRequest,
    db: Session = Depends(get_db),
    actor: Actor = Depends(get_actor),
):
    if actor.role != "internal":
        raise HTTPException(status_code=403, detail="You do not have permission to do this")

    # Same reference sent twice = same refund (no double refund)
    existing = db.query(Refund).filter(Refund.reference == data.reference).first()
    if existing:
        return refund_out(existing)

    payment = (
        db.query(Payment)
        .filter(Payment.order_id == data.order_id, Payment.status == "succeeded")
        .first()
    )
    if payment is None:
        raise HTTPException(status_code=409, detail="There is no completed payment for this order")
    refunded = (
        db.query(func.coalesce(func.sum(Refund.amount), 0.0))
        .filter(Refund.payment_id == payment.id)
        .scalar()
    )
    if refunded + data.amount > payment.amount + 0.005:
        raise HTTPException(status_code=409, detail="The refund is more than the amount paid")

    refund = Refund(
        reference=data.reference,
        payment_id=payment.id,
        order_id=data.order_id,
        amount=data.amount,
        reason=data.reason,
    )
    db.add(refund)
    add_audit(db, None, "refund_processed", f"{data.reference} {data.amount:.2f}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Refund).filter(Refund.reference == data.reference).first()
        if existing:
            return refund_out(existing)
        raise HTTPException(status_code=409, detail="Duplicate refund reference")
    db.refresh(refund)
    return refund_out(refund)