from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import schemas
from .database import Base, engine, get_db
from .dependencies import Actor, require_admin, require_internal, require_user
from .models import AuditLog, Coupon, CouponRedemption, utcnow

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Coupon and Discount Service")


# ---------- helper functions ----------

def add_audit(db: Session, user_id: Optional[int], action: str, detail: str = ""):
    db.add(AuditLog(user_id=user_id, action=action, detail=detail))


def coupon_status(c: Coupon) -> str:
    now = utcnow()
    if not c.is_active:
        return "inactive"
    if now > c.expires_at:
        return "expired"
    if now < c.valid_from:
        return "scheduled"
    if c.total_usage_limit is not None and c.times_redeemed >= c.total_usage_limit:
        return "exhausted"
    return "active"


def to_out(c: Coupon) -> schemas.CouponOut:
    return schemas.CouponOut(
        id=c.id,
        code=c.code,
        discount_type=c.discount_type,
        discount_value=c.discount_value,
        max_discount_amount=c.max_discount_amount,
        min_purchase_amount=c.min_purchase_amount,
        valid_from=c.valid_from,
        expires_at=c.expires_at,
        total_usage_limit=c.total_usage_limit,
        per_user_limit=c.per_user_limit,
        times_redeemed=c.times_redeemed,
        is_active=c.is_active,
        status=coupon_status(c),
        created_at=c.created_at,
    )


def find_coupon(db: Session, code: str) -> Optional[Coupon]:
    return db.query(Coupon).filter(Coupon.code == code.strip().upper()).first()


def calc_discount(c: Coupon, cart_total: float) -> float:
    if c.discount_type == "percentage":
        discount = cart_total * c.discount_value / 100
        if c.max_discount_amount is not None:
            discount = min(discount, c.max_discount_amount)
    else:
        discount = c.discount_value
    discount = min(discount, cart_total)  # discount can never be more than the cart
    return round(discount, 2)


def user_uses(db: Session, coupon_id: int, user_id: int) -> int:
    return (
        db.query(func.count(CouponRedemption.id))
        .filter(
            CouponRedemption.coupon_id == coupon_id,
            CouponRedemption.user_id == user_id,
            CouponRedemption.status == "redeemed",
        )
        .scalar()
    )


def ensure_usable(db: Session, coupon: Optional[Coupon], user_id: int, cart_total: float):
    if coupon is None:
        raise HTTPException(status_code=404, detail="Coupon code not found")
    if not coupon.is_active:
        raise HTTPException(status_code=400, detail="This coupon is not active")
    now = utcnow()
    if now < coupon.valid_from:
        raise HTTPException(status_code=400, detail="This coupon is not valid yet")
    if now > coupon.expires_at:
        raise HTTPException(status_code=400, detail="This coupon has expired")
    if coupon.total_usage_limit is not None and coupon.times_redeemed >= coupon.total_usage_limit:
        raise HTTPException(status_code=400, detail="This coupon has reached its usage limit")
    if user_uses(db, coupon.id, user_id) >= coupon.per_user_limit:
        raise HTTPException(
            status_code=400,
            detail="You have already used this coupon the maximum number of times",
        )
    if cart_total < coupon.min_purchase_amount:
        raise HTTPException(
            status_code=400,
            detail=f"A minimum purchase of {coupon.min_purchase_amount:.2f} is required for this coupon",
        )


def redeem_output(r: CouponRedemption, code: str, cart_total: float) -> schemas.RedeemResponse:
    return schemas.RedeemResponse(
        order_reference=r.order_reference,
        code=code,
        discount_amount=r.discount_amount,
        final_total=round(cart_total - r.discount_amount, 2),
        status=r.status,
    )


# ---------- APIs ----------

@app.get("/health")
def health():
    return {"status": "ok", "service": "coupon"}


@app.post("/coupons", response_model=schemas.CouponOut, status_code=201)
def create_coupon(
    data: schemas.CouponCreate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_admin),
):
    if find_coupon(db, data.code):
        raise HTTPException(status_code=409, detail="This coupon code already exists")
    coupon = Coupon(
        code=data.code,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        max_discount_amount=data.max_discount_amount,
        min_purchase_amount=data.min_purchase_amount,
        valid_from=data.valid_from or utcnow(),
        expires_at=data.expires_at,
        total_usage_limit=data.total_usage_limit,
        per_user_limit=data.per_user_limit,
        created_by=actor.user_id,
    )
    db.add(coupon)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This coupon code already exists")
    add_audit(db, actor.user_id, "coupon_created", coupon.code)
    db.commit()
    db.refresh(coupon)
    return to_out(coupon)


@app.get("/coupons", response_model=schemas.CouponPage)
def list_coupons(
    active_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_admin),
):
    query = db.query(Coupon)
    if active_only:
        now = utcnow()
        query = query.filter(
            Coupon.is_active == True,  # noqa: E712
            Coupon.expires_at >= now,
            or_(Coupon.total_usage_limit.is_(None), Coupon.times_redeemed < Coupon.total_usage_limit),
        )
    total = query.count()
    rows = (
        query.order_by(Coupon.created_at.desc(), Coupon.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.CouponPage(
        items=[to_out(c) for c in rows], total=total, page=page, page_size=page_size
    )


@app.post("/coupons/validate", response_model=schemas.ValidateResponse)
def validate_coupon(
    data: schemas.ValidateRequest,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_user),
):
    coupon = find_coupon(db, data.code)
    ensure_usable(db, coupon, actor.user_id, data.cart_total)
    discount = calc_discount(coupon, data.cart_total)
    return schemas.ValidateResponse(
        valid=True,
        code=coupon.code,
        discount_type=coupon.discount_type,
        discount_amount=discount,
        cart_total=data.cart_total,
        final_total=round(data.cart_total - discount, 2),
        message="Coupon applied",
    )


@app.post("/coupons/redeem", response_model=schemas.RedeemResponse)
def redeem_coupon(
    data: schemas.RedeemRequest,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_internal),
):
    """Called by the Order service when an order is placed."""
    # Same order sent twice = same result (no double use)
    existing = (
        db.query(CouponRedemption)
        .filter(CouponRedemption.order_reference == data.order_reference)
        .first()
    )
    if existing:
        if existing.status == "redeemed":
            coupon = db.get(Coupon, existing.coupon_id)
            return redeem_output(existing, coupon.code, data.cart_total)
        raise HTTPException(
            status_code=409, detail="This order reference was already used and released"
        )

    coupon = find_coupon(db, data.code)
    ensure_usable(db, coupon, data.user_id, data.cart_total)
    discount = calc_discount(coupon, data.cart_total)

    # Claim one use in a single database step, so two orders at the
    # same moment cannot go over the usage limit.
    claimed = db.execute(
        update(Coupon)
        .where(
            Coupon.id == coupon.id,
            or_(Coupon.total_usage_limit.is_(None), Coupon.times_redeemed < Coupon.total_usage_limit),
        )
        .values(times_redeemed=Coupon.times_redeemed + 1)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="This coupon has reached its usage limit")

    redemption = CouponRedemption(
        coupon_id=coupon.id,
        user_id=data.user_id,
        order_reference=data.order_reference,
        discount_amount=discount,
        status="redeemed",
    )
    db.add(redemption)
    add_audit(db, data.user_id, "coupon_redeemed", f"{coupon.code} for {data.order_reference}")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(CouponRedemption)
            .filter(CouponRedemption.order_reference == data.order_reference)
            .first()
        )
        if existing and existing.status == "redeemed":
            return redeem_output(existing, coupon.code, data.cart_total)
        raise HTTPException(status_code=409, detail="Duplicate order reference")
    db.refresh(redemption)
    return redeem_output(redemption, coupon.code, data.cart_total)


@app.post(
    "/coupons/redemptions/{order_reference}/release",
    response_model=schemas.RedeemResponse,
)
def release_redemption(
    order_reference: str,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_internal),
):
    """Called when an order is cancelled: the coupon use is given back."""
    redemption = (
        db.query(CouponRedemption)
        .filter(CouponRedemption.order_reference == order_reference)
        .first()
    )
    if redemption is None:
        raise HTTPException(status_code=404, detail="No coupon was used for this order")
    coupon = db.get(Coupon, redemption.coupon_id)
    if redemption.status == "released":
        return redeem_output(redemption, coupon.code, redemption.discount_amount)

    marked = db.execute(
        update(CouponRedemption)
        .where(CouponRedemption.id == redemption.id, CouponRedemption.status == "redeemed")
        .values(status="released")
        .execution_options(synchronize_session=False)
    )
    if marked.rowcount == 1:
        db.execute(
            update(Coupon)
            .where(Coupon.id == coupon.id, Coupon.times_redeemed > 0)
            .values(times_redeemed=Coupon.times_redeemed - 1)
            .execution_options(synchronize_session=False)
        )
        add_audit(db, redemption.user_id, "coupon_released", f"{coupon.code} for {order_reference}")
    db.commit()
    db.refresh(redemption)
    return redeem_output(redemption, coupon.code, redemption.discount_amount)


@app.get("/coupons/{coupon_id}", response_model=schemas.CouponOut)
def get_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_admin),
):
    coupon = db.get(Coupon, coupon_id)
    if coupon is None:
        raise HTTPException(status_code=404, detail="Coupon not found")
    return to_out(coupon)


@app.patch("/coupons/{coupon_id}", response_model=schemas.CouponOut)
def update_coupon(
    coupon_id: int,
    data: schemas.CouponUpdate,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_admin),
):
    coupon = db.get(Coupon, coupon_id)
    if coupon is None:
        raise HTTPException(status_code=404, detail="Coupon not found")
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")
    for field, value in changes.items():
        if value is None:
            raise HTTPException(status_code=422, detail=f"{field} cannot be empty")
    if "max_discount_amount" in changes and coupon.discount_type != "percentage":
        raise HTTPException(
            status_code=400, detail="max_discount_amount is only for percentage coupons"
        )
    if "total_usage_limit" in changes and changes["total_usage_limit"] < coupon.times_redeemed:
        raise HTTPException(
            status_code=400,
            detail="Usage limit cannot be lower than the number of times already used",
        )
    for field, value in changes.items():
        setattr(coupon, field, value)
    add_audit(db, actor.user_id, "coupon_updated", f"{coupon.code}: {', '.join(changes)}")
    db.commit()
    db.refresh(coupon)
    return to_out(coupon)