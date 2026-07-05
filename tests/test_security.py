import pytest
import jwt as pyjwt

from app.core.security import hash_password, verify_password, create_jwt, decode_jwt


def test_password_hash_and_verify():
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_jwt_round_trip():
    token = create_jwt("user-123")
    payload = decode_jwt(token)
    assert payload["sub"] == "user-123"


def test_jwt_invalid_signature_raises():
    token = create_jwt("user-123")
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(pyjwt.InvalidTokenError):
        decode_jwt(tampered)
