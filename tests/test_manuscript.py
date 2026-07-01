def _signup_and_login(client, login_id="mstester"):
    client.post(
        "/api/auth/signup",
        json={"login_id": login_id, "password": "password123", "nickname": "테스터"},
    )


def test_create_manuscript_requires_auth(client):
    # 로그인 쿠키 없이 원고 생성을 시도하면 401을 반환해야 한다.
    response = client.post(
        "/api/manuscripts", json={"topic": "FastAPI 학습", "concept": "til"}
    )
    assert response.status_code == 401


def test_create_and_get_manuscript(client):
    # 로그인한 사용자가 원고를 생성하면 201로 응답하고,
    # 생성된 id로 다시 조회했을 때 동일한 원고를 돌려받아야 한다.
    _signup_and_login(client)
    response = client.post(
        "/api/manuscripts", json={"topic": "FastAPI 학습", "concept": "til"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["topic"] == "FastAPI 학습"
    assert body["concept"] == "til"
    assert body["status"] == "drafting"

    manuscript_id = body["id"]
    response = client.get(f"/api/manuscripts/{manuscript_id}")
    assert response.status_code == 200
    assert response.json()["id"] == manuscript_id


def test_create_manuscript_invalid_concept_returns_422(client):
    # concept이 ConceptType에 정의되지 않은 값이면 Pydantic 검증에서 422를 반환해야 한다.
    _signup_and_login(client, login_id="badconcept")
    response = client.post(
        "/api/manuscripts", json={"topic": "A", "concept": "not_a_real_concept"}
    )
    assert response.status_code == 422
