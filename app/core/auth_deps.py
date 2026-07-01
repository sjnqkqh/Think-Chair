import uuid

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_database_session
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_jwt
from app.models.user import User


def require_user(
    request: Request, db: Session = Depends(get_database_session)
) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise UnauthorizedError("로그인이 필요합니다.")

    try:
        payload = decode_jwt(token)
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.InvalidTokenError, ValueError):
        raise UnauthorizedError("유효하지 않은 인증입니다.")

    if not user:
        raise UnauthorizedError("유효하지 않은 인증입니다.")

    return user
