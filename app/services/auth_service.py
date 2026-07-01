import logging

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import create_jwt, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest

logger = logging.getLogger(__name__)


def signup_user(db: Session, payload: SignupRequest) -> tuple[User, str]:
    if db.query(User).filter(User.login_id == payload.login_id).first():
        logger.warning("signup rejected: login_id=%s already exists", payload.login_id)
        raise ConflictError("이미 사용 중인 아이디입니다.")

    user = User(
        login_id=payload.login_id,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("user signed up: user_id=%s login_id=%s", user.id, user.login_id)
    return user, create_jwt(str(user.id))


def authenticate_user(db: Session, payload: LoginRequest) -> tuple[User, str]:
    user = db.query(User).filter(User.login_id == payload.login_id).first()
    if not user or not verify_password(payload.password, user.password_hash):
        logger.warning("login failed: login_id=%s", payload.login_id)
        raise UnauthorizedError("아이디 또는 비밀번호가 올바르지 않습니다.")

    logger.info("user logged in: user_id=%s login_id=%s", user.id, user.login_id)
    return user, create_jwt(str(user.id))
