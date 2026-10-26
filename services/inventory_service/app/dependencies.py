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


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_actor(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    x_internal_key: Optional[str] = Header(default=None),
) -> Actor:
    # Other services prove who they are with the internal key
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
        return Actor(user_id=int(payload["sub"]), role=payload["role"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthorized("Invalid or expired token")


def require_staff(actor: Actor = Depends(get_actor)) -> Actor:
    if actor.role not in STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to do this",
        )
    return actor


def require_staff_or_internal(actor: Actor = Depends(get_actor)) -> Actor:
    if actor.role not in STAFF_ROLES and actor.role != "internal":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to do this",
        )
    return actor