import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import clients, schemas
from .database import Base, SessionLocal, engine, get_db
from .dependencies import Actor, get_optional_user, require_admin, require_user
from .models import AuditLog, ProductRating, Review

Base.metadata.create_all(bind=engine)
logger = logging.getLogger("reviews")


# ---------- helper functions ----------

def add_audit(db: Session, user_id: Optional[int], action: str, detail: str = ""):
    db.add(AuditLog(user_id=user_id, action=action, detail=detail))


def rating_summary(db: Session, product_id: int) -> schemas.RatingSummary:
    rows = (
        db.query(Review.rating, func.count(Review.id))
        .filter(Review.product_id == product_id, Review.status == "approved")
        .group_by(Review.rating)
        .all()
    )
    distribution = {str(star): 0 for star in range(1, 6)}
    total = 0
    weighted = 0
    for star, count in rows:
        distribution[str(star)] = count
        total += count
        weighted += star * count
    average = round(weighted / total, 2) if total else 0.0
    return schemas.RatingSummary(average=average, count=total, distribution=distribution)


def mark_rating_changed(db: Session, product_id: int):
    """Save the new average, marked as 'not yet sent to the Product service'."""
    summary = rating_summary(db, product_id)
    row = db.get(ProductRating, product_id)
    if row is None:
        row = ProductRating(product_id=product_id)
        db.add(row)
    row.average = summary.average
    row.count = summary.count
    row.synced = False


def sync_rating(product_id: int):
    """Send the average to the Product service (the 1-minute job retries if this fails)."""
    db = SessionLocal()
    try:
        row = db.get(ProductRating, product_id)
        if row and not row.synced and clients.push_rating(product_id, row.average, row.count):
            row.synced = True
            db.commit()
    finally:
        db.close()


def to_out(r: Review, current_user_id: Optional[int]) -> schemas.ReviewOut:
    return schemas.ReviewOut(
        id=r.id,
        product_id=r.product_id,
        reviewer_name=r.reviewer_name,
        rating=r.rating,
        title=r.title,
        comment=r.comment,
        is_mine=current_user_id is not None and r.user_id == current_user_id,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def to_my_out(r: Review) -> schemas.MyReviewOut:
    base = to_out(r, r.user_id).model_dump()
    return schemas.MyReviewOut(**base, status=r.status, moderation_note=r.moderation_note)


def to_admin_out(r: Review) -> schemas.AdminReviewOut:
    return schemas.AdminReviewOut(
        id=r.id,
        product_id=r.product_id,
        user_id=r.user_id,
        reviewer_name=r.reviewer_name,
        rating=r.rating,
        title=r.title,
        comment=r.comment,
        status=r.status,
        moderation_note=r.moderation_note,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def get_own_review(db: Session, review_id: int, user_id: int) -> Review:
    review = (
        db.query(Review).filter(Review.id == review_id, Review.user_id == user_id).first()
    )
    if review is None:  # someone else's review looks like it does not exist
        raise HTTPException(status_code=404, detail="Review not found")
    return review


# ---------- background job: retry sending averages to the Product service ----------

def run_resync():
    db = SessionLocal()
    try:
        ids = [row.product_id for row in db.query(ProductRating).filter(ProductRating.synced == False).all()]  # noqa: E712
    finally:
        db.close()
    for product_id in ids:
        sync_rating(product_id)


async def resync_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(run_resync)
        except Exception:
            logger.exception("Rating resync job failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(resync_loop())
    yield
    task.cancel()


app = FastAPI(title="Review and Rating Service", lifespan=lifespan)


# ---------- APIs ----------

@app.get("/health")
def health():
    return {"status": "ok", "service": "review"}


@app.post("/reviews", response_model=schemas.MyReviewOut, status_code=201)
def create_review(
    data: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    user: Actor = Depends(require_user),
):
    already = (
        db.query(Review.id)
        .filter(Review.user_id == user.user_id, Review.product_id == data.product_id)
        .first()
    )
    if already:
        raise HTTPException(
            status_code=409,
            detail="You have already reviewed this product. You can edit your review instead.",
        )
    eligibility = clients.check_eligibility(user.user_id, data.product_id)
    if not eligibility["eligible"]:
        raise HTTPException(
            status_code=403,
            detail="Only customers who received this product can review it",
        )
    review = Review(
        product_id=data.product_id,
        user_id=user.user_id,
        order_id=eligibility["order_id"],
        reviewer_name=clients.get_display_name(user.token),
        rating=data.rating,
        title=data.title.strip() if data.title else None,
        comment=data.comment.strip(),
    )
    db.add(review)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You have already reviewed this product")
    mark_rating_changed(db, data.product_id)
    add_audit(db, user.user_id, "review_created", f"product {data.product_id}")
    db.commit()
    db.refresh(review)
    sync_rating(data.product_id)
    return to_my_out(review)


@app.get("/reviews/my-reviews", response_model=list[schemas.MyReviewOut])
def my_reviews(
    db: Session = Depends(get_db),
    user: Actor = Depends(require_user),
):
    rows = (
        db.query(Review)
        .filter(Review.user_id == user.user_id)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .all()
    )
    return [to_my_out(r) for r in rows]


@app.get("/reviews", response_model=schemas.AdminReviewPage)
def list_reviews_for_moderation(
    status: Optional[Literal["approved", "hidden"]] = None,
    product_id: Optional[int] = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: Actor = Depends(require_admin),
):
    query = db.query(Review)
    if status:
        query = query.filter(Review.status == status)
    if product_id:
        query = query.filter(Review.product_id == product_id)
    total = query.count()
    rows = (
        query.order_by(Review.created_at.desc(), Review.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.AdminReviewPage(
        items=[to_admin_out(r) for r in rows], total=total, page=page, page_size=page_size
    )


@app.get("/products/{product_id}/reviews", response_model=schemas.ProductReviewPage)
def product_reviews(
    product_id: int,
    sort: Literal["newest", "highest", "lowest"] = "newest",
    rating: Optional[int] = Query(None, ge=1, le=5),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: Optional[Actor] = Depends(get_optional_user),
):
    query = db.query(Review).filter(Review.product_id == product_id, Review.status == "approved")
    if rating:
        query = query.filter(Review.rating == rating)
    if sort == "highest":
        ordering = (Review.rating.desc(), Review.created_at.desc(), Review.id.desc())
    elif sort == "lowest":
        ordering = (Review.rating.asc(), Review.created_at.desc(), Review.id.desc())
    else:
        ordering = (Review.created_at.desc(), Review.id.desc())
    total = query.count()
    rows = query.order_by(*ordering).offset((page - 1) * page_size).limit(page_size).all()
    current_id = user.user_id if user else None
    return schemas.ProductReviewPage(
        summary=rating_summary(db, product_id),
        items=[to_out(r, current_id) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.put("/reviews/{review_id}", response_model=schemas.MyReviewOut)
def update_review(
    review_id: int,
    data: schemas.ReviewUpdate,
    db: Session = Depends(get_db),
    user: Actor = Depends(require_user),
):
    review = get_own_review(db, review_id, user.user_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")
    for field, value in changes.items():
        if value is None and field != "title":
            raise HTTPException(status_code=422, detail=f"{field} cannot be empty")
        setattr(review, field, value.strip() if isinstance(value, str) else value)
    mark_rating_changed(db, review.product_id)
    add_audit(db, user.user_id, "review_updated", f"review {review.id}")
    db.commit()
    db.refresh(review)
    sync_rating(review.product_id)
    return to_my_out(review)


@app.delete("/reviews/{review_id}", status_code=204)
def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_user),
):
    review = db.get(Review, review_id)
    allowed = review is not None and (
        actor.role == "administrator" or review.user_id == actor.user_id
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Review not found")
    product_id = review.product_id
    db.delete(review)
    db.flush()
    mark_rating_changed(db, product_id)
    add_audit(db, actor.user_id, "review_deleted", f"review {review_id}")
    db.commit()
    sync_rating(product_id)
    return Response(status_code=204)


@app.patch("/reviews/{review_id}/moderation", response_model=schemas.AdminReviewOut)
def moderate_review(
    review_id: int,
    data: schemas.ModerationRequest,
    db: Session = Depends(get_db),
    admin: Actor = Depends(require_admin),
):
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    review.status = data.status
    review.moderation_note = data.note
    db.flush()
    mark_rating_changed(db, review.product_id)
    add_audit(db, admin.user_id, "review_moderated", f"review {review.id} -> {data.status}")
    db.commit()
    db.refresh(review)
    sync_rating(review.product_id)
    return to_admin_out(review)