import hmac
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

optional_bearer = HTTPBearer(auto_error=False)

STAFF_ROLES = ("administrator", "inventory_manager")


@dataclass
class Actor:
    user_id: Optional[int]
    role: str  # "internal" means another service is calling us
    token: Optional[str] = None  # the login token, passed on to the Cart service


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to do this",
    )


def get_actor(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    x_internal_key: Optional[str] = Header(default=None),
) -> Actor:
    if x_internal_key is not None:
        expected = settings.INTERNAL_API_KEY
        if expected and hmac.compare_digest(
            x_internal_key.encode("utf-8"), expected.encode("utf-8")
        ):
            return Actor(user_id=None, role="internal")
        raise _unauthorized("Invalid internal key")

    if credentials is None:
        raise _unauthorized("Not authenticated")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Wrong token type")
        return Actor(
            user_id=int(payload["sub"]),
            role=payload["role"],
            token=credentials.credentials,
        )
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthorized("Invalid or expired token")


def require_user(actor: Actor = Depends(get_actor)) -> Actor:
    if actor.user_id is None:
        raise _forbidden()
    return actor


def require_staff(actor: Actor = Depends(get_actor)) -> Actor:
    if actor.role not in STAFF_ROLES:
        raise _forbidden()
    return actor


def require_internal(actor: Actor = Depends(get_actor)) -> Actor:
    if actor.role != "internal":
        raise _forbidden()
    return actor