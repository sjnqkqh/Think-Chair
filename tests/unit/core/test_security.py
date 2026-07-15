import pytest

from app.core.security import hash_password, verify_password, create_jwt, decode_jwt

pytestmark = pytest.mark.unit


def test_password_hash_and_verify():
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_jwt_round_trip():
    token = create_jwt("user-123")
    payload = decode_jwt(token)
    assert payload["sub"] == "user-123"
