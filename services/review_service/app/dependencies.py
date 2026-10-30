from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

bearer_scheme = HTTPBearer()
optional_bearer = HTTPBearer(auto_error=False)


@dataclass
class Actor:
    user_id: int
    role: str
    token: str  # passed on to the Auth service to read the reviewer's name


def _read_token(token: str) -> Actor:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Wrong token type")
        return Actor(user_id=int(payload["sub"]), role=payload["role"], token=token)
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Actor:
    return _read_token(credentials.credentials)


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
) -> Optional[Actor]:
    if credentials is None:
        return None
    return _read_token(credentials.credentials)


def require_admin(actor: Actor = Depends(require_user)) -> Actor:
    if actor.role != "administrator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to do this",
        )
    return actor