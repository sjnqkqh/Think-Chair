from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_database_session
from app.schemas.auth import LoginRequest, SignupRequest, UserResponse
from app.services.auth_service import authenticate_user, signup_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "access_token"


@router.post("/signup", response_model=UserResponse, status_code=201)
def signup(
    payload: SignupRequest,
    response: Response,
    db: Session = Depends(get_database_session),
):
    user, token = signup_user(db, payload)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
    return UserResponse(id=str(user.id), login_id=user.login_id, nickname=user.nickname)


@router.post("/login", response_model=UserResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_database_session),
):
    user, token = authenticate_user(db, payload)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
    return UserResponse(id=str(user.id), login_id=user.login_id, nickname=user.nickname)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
