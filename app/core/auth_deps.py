import uuid

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_database_session
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_jwt
from app.logging import get_logger
from app.models.user import User

logger = get_logger(__name__)


def require_user(request: Request, db: Session = Depends(get_database_session)) -> User:
    token = request.cookies.get("access_token")
    if not token:
        logger.warning(
            "auth.request.unauthenticated",
            reason="missing_access_token",
            path=request.url.path,
        )
        raise UnauthorizedError("로그인이 필요합니다.")

    try:
        payload = decode_jwt(token)
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.InvalidTokenError, ValueError):
        logger.warning(
            "auth.request.unauthenticated",
            reason="invalid_token",
            path=request.url.path,
        )
        raise UnauthorizedError("유효하지 않은 인증입니다.")

    if not user:
        logger.warning(
            "auth.request.unauthenticated",
            reason="user_not_found",
            path=request.url.path,
        )
        raise UnauthorizedError("유효하지 않은 인증입니다.")

    return user
