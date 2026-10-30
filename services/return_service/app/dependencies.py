from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

bearer_scheme = HTTPBearer()

STAFF_ROLES = ("administrator", "inventory_manager")


@dataclass
class Actor:
    user_id: int
    role: str


def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Actor:
    try:
        payload = jwt.decode(
            credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Wrong token type")
        return Actor(user_id=int(payload["sub"]), role=payload["role"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def require_staff(actor: Actor = Depends(require_user)) -> Actor:
    if actor.role not in STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to do this",
        )
    return actor