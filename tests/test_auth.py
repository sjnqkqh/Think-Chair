def test_signup_success(client):
    res = client.post(
        "/api/auth/signup",
        json={"login_id": "tester1", "password": "password123", "nickname": "테스터"},
    )
    assert res.status_code == 201
    assert res.json()["login_id"] == "tester1"
    assert "access_token" in res.cookies


def test_signup_duplicate_login_id(client):
    client.post(
        "/api/auth/signup",
        json={"login_id": "dupuser", "password": "password123", "nickname": "A"},
    )
    res = client.post(
        "/api/auth/signup",
        json={"login_id": "dupuser", "password": "password123", "nickname": "B"},
    )
    assert res.status_code == 409


def test_login_success(client):
    client.post(
        "/api/auth/signup",
        json={"login_id": "loginuser", "password": "password123", "nickname": "로그인"},
    )
    res = client.post(
        "/api/auth/login",
        json={"login_id": "loginuser", "password": "password123"},
    )
    assert res.status_code == 200
    assert "access_token" in res.cookies


def test_login_wrong_password(client):
    client.post(
        "/api/auth/signup",
        json={"login_id": "wrongpw", "password": "password123", "nickname": "X"},
    )
    res = client.post(
        "/api/auth/login",
        json={"login_id": "wrongpw", "password": "incorrect"},
    )
    assert res.status_code == 401


def test_login_unknown_user(client):
    res = client.post(
        "/api/auth/login",
        json={"login_id": "nobody", "password": "whatever"},
    )
    assert res.status_code == 401


def test_logout_clears_cookie(client):
    res = client.post("/api/auth/logout")
    assert res.status_code == 204
