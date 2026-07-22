import pytest

pytestmark = pytest.mark.integration


def test_signup_success(client):
    # 회원가입 성공 시 201과 함께 access_token 쿠키가 발급되어야 한다.
    response = client.post(
        "/api/auth/signup",
        json={"login_id": "tester1", "password": "password123", "nickname": "테스터"},
    )
    assert response.status_code == 201
    assert response.json()["login_id"] == "tester1"
    assert "access_token" in response.cookies


def test_signup_duplicate_login_id(client):
    # 이미 존재하는 login_id로 재가입을 시도하면 409(Conflict)를 반환해야 한다.
    client.post(
        "/api/auth/signup",
        json={"login_id": "dupuser", "password": "password123", "nickname": "A"},
    )
    response = client.post(
        "/api/auth/signup",
        json={"login_id": "dupuser", "password": "password123", "nickname": "B"},
    )
    assert response.status_code == 409


def test_login_success(client):
    # 가입된 계정으로 로그인하면 200과 함께 access_token 쿠키가 재발급되어야 한다.
    client.post(
        "/api/auth/signup",
        json={"login_id": "loginuser", "password": "password123", "nickname": "로그인"},
    )
    response = client.post(
        "/api/auth/login",
        json={"login_id": "loginuser", "password": "password123"},
    )
    assert response.status_code == 200
    assert "access_token" in response.cookies


def test_login_wrong_password(client):
    # 비밀번호가 틀리면 401(Unauthorized)을 반환해야 한다.
    client.post(
        "/api/auth/signup",
        json={"login_id": "wrongpw", "password": "password123", "nickname": "X"},
    )
    response = client.post(
        "/api/auth/login",
        json={"login_id": "wrongpw", "password": "incorrect"},
    )
    assert response.status_code == 401


def test_login_failure_is_logged(client, caplog):
    # 로그인 실패는 login_id가 포함된 warning 로그를 남겨서 외부에서 원인을 추적할 수 있어야 한다.
    client.post(
        "/api/auth/signup",
        json={"login_id": "logtarget", "password": "password123", "nickname": "X"},
    )
    with caplog.at_level("WARNING", logger="app.services.auth_service"):
        client.post(
            "/api/auth/login",
            json={"login_id": "logtarget", "password": "incorrect"},
        )
    assert any("auth.login.failed" in record.message for record in caplog.records)
    assert any("logtarget" in record.message for record in caplog.records)


def test_login_unknown_user(client):
    # 존재하지 않는 login_id로 로그인 시도해도 401을 반환해야 한다(계정 존재 여부 노출 방지).
    response = client.post(
        "/api/auth/login",
        json={"login_id": "nobody", "password": "whatever"},
    )
    assert response.status_code == 401


def test_logout_clears_cookie(client):
    # 로그아웃 요청은 인증 여부와 무관하게 204와 함께 쿠키 삭제 응답을 반환해야 한다.
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
