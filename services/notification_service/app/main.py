import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from . import schemas
from .config import settings
from .consumer import NotificationConsumer
from .database import Base, engine, get_db
from .dependencies import STAFF_ROLES, Actor, require_admin, require_user
from .models import Notification

logging.basicConfig(level=logging.INFO, format="%(message)s")
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer = None
    if settings.RABBITMQ_URL:
        consumer = NotificationConsumer()
        consumer.start()
    else:
        logging.warning("RABBITMQ_URL is not set: notifications will not be received")
    yield
    if consumer:
        consumer.stop()


app = FastAPI(title="Notification Service", lifespan=lifespan)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def visible_to(query, actor: Actor):
    """Customers see only their own. Staff also see the admin alerts."""
    if actor.role in STAFF_ROLES:
        return query.filter(
            or_(Notification.user_id == actor.user_id, Notification.audience == "admin")
        )
    return query.filter(Notification.user_id == actor.user_id, Notification.audience == "user")


def to_out(n: Notification) -> schemas.NotificationOut:
    return schemas.NotificationOut(
        id=n.id,
        type=n.event_type,
        title=n.title,
        message=n.message,
        data=json.loads(n.data or "{}"),
        is_read=n.is_read,
        created_at=n.created_at,
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "notification"}


@app.get("/notifications", response_model=schemas.NotificationPage)
def list_notifications(
    unread_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_user),
):
    base = visible_to(db.query(Notification), actor)
    unread_count = base.filter(Notification.is_read == False).count()  # noqa: E712
    query = base.filter(Notification.is_read == False) if unread_only else base  # noqa: E712
    total = query.count()
    rows = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return schemas.NotificationPage(
        items=[to_out(n) for n in rows],
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
    )


# These two must stay ABOVE /notifications/{notification_id}/read
@app.get("/notifications/history", response_model=schemas.HistoryPage)
def notification_history(
    event_type: Optional[str] = Query(None, max_length=60),
    audience: Optional[str] = Query(None, pattern="^(user|admin)$"),
    user_id: Optional[int] = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: Actor = Depends(require_admin),
):
    query = db.query(Notification)
    if event_type:
        query = query.filter(Notification.event_type == event_type)
    if audience:
        query = query.filter(Notification.audience == audience)
    if user_id:
        query = query.filter(Notification.user_id == user_id)
    total = query.count()
    rows = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        schemas.HistoryItem(**to_out(n).model_dump(), user_id=n.user_id, audience=n.audience)
        for n in rows
    ]
    return schemas.HistoryPage(items=items, total=total, page=page, page_size=page_size)


@app.post("/notifications/read-all", response_model=schemas.ReadAllResult)
def mark_all_read(
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_user),
):
    ids = [
        n.id
        for n in visible_to(db.query(Notification.id), actor)
        .filter(Notification.is_read == False)  # noqa: E712
        .all()
    ]
    if ids:
        db.execute(
            update(Notification)
            .where(Notification.id.in_(ids))
            .values(is_read=True, read_at=utcnow())
        )
        db.commit()
    return schemas.ReadAllResult(marked_read=len(ids))


@app.patch("/notifications/{notification_id}/read", response_model=schemas.NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    actor: Actor = Depends(require_user),
):
    notification = (
        visible_to(db.query(Notification), actor)
        .filter(Notification.id == notification_id)
        .first()
    )
    if notification is None:  # someone else's notification looks like it does not exist
        raise HTTPException(status_code=404, detail="Notification not found")
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = utcnow()
        db.commit()
        db.refresh(notification)
    return to_out(notification)