import time
from collections import defaultdict
from datetime import timedelta

from fastapi import Depends, FastAPI, HTTPException, Request, status
from sqlalchemy.orm import Session

from . import models, schemas
from .config import settings
from .database import Base, engine, get_db
from .dependencies import get_current_user
from .models import utcnow
from .security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Auth Service")

# Simple login rate limit (we will move this to Redis later)
LOGIN_LIMIT = 10
LOGIN_WINDOW_SECONDS = 60
login_attempts = defaultdict(list)


def check_login_rate_limit(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    recent = [t for t in login_attempts[ip] if now - t < LOGIN_WINDOW_SECONDS]
    if len(recent) >= LOGIN_LIMIT:
        login_attempts[ip] = recent
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )
    recent.append(now)
    login_attempts[ip] = recent


def add_audit(db: Session, user_id, action: str, detail: str = ""):
    db.add(models.AuditLog(user_id=user_id, action=action, detail=detail))
    db.commit()


def issue_tokens(db: Session, user: models.User) -> schemas.TokenResponse:
    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token()
    db.add(
        models.RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh),
            expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()
    return schemas.TokenResponse(access_token=access, refresh_token=refresh)


@app.get("/health")
def health():
    return {"status": "ok", "service": "auth"}


@app.post(
    "/auth/register",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
)
def register(data: schemas.RegisterRequest, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )
    user = models.User(
        email=email,
        full_name=data.full_name.strip(),
        hashed_password=hash_password(data.password),
        role="customer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    add_audit(db, user.id, "register", f"New customer {user.email}")
    return user


@app.post("/auth/login", response_model=schemas.TokenResponse)
def login(
    data: schemas.LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    check_login_rate_limit(request)
    user = (
        db.query(models.User)
        .filter(models.User.email == data.email.lower())
        .first()
    )
    if (
        user is None
        or not user.is_active
        or not verify_password(data.password, user.hashed_password)
    ):
        add_audit(db, user.id if user else None, "login_failed", data.email.lower())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    add_audit(db, user.id, "login_success")
    return issue_tokens(db, user)


@app.post("/auth/refresh", response_model=schemas.TokenResponse)
def refresh(data: schemas.RefreshRequest, db: Session = Depends(get_db)):
    stored = (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == hash_refresh_token(data.refresh_token))
        .first()
    )
    if stored is None or stored.revoked or stored.expires_at < utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    user = db.get(models.User, stored.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    stored.revoked = True  # each refresh token can be used only once
    db.commit()
    return issue_tokens(db, user)


@app.get("/auth/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user