from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

bearer_scheme = HTTPBearer()


@dataclass
class Actor:
    user_id: int
    role: str
    token: str  # passed on to the other services, so they apply their own permission checks


def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> Actor:
    try:
        payload = jwt.decode(
            credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Wrong token type")
        return Actor(
            user_id=int(payload["sub"]), role=payload["role"], token=credentials.credentials
        )
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )