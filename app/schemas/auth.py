from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    login_id: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    nickname: str = Field(..., min_length=1, max_length=64)


class LoginRequest(BaseModel):
    login_id: str
    password: str


class UserResponse(BaseModel):
    id: str
    login_id: str
    nickname: str
