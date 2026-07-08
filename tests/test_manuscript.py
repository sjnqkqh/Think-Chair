import uuid

from app.models.manuscript import ManuscriptVersion


def _signup_and_login(client, login_id="mstester"):
    client.post(
        "/api/auth/signup",
        json={"login_id": login_id, "password": "password123", "nickname": "테스터"},
    )


def test_create_manuscript_requires_auth(client):
    # 로그인 쿠키 없이 원고 생성을 시도하면 401을 반환해야 한다.
    response = client.post(
        "/api/manuscripts", json={"topic": "FastAPI 학습", "concept": "TIL"}
    )
    assert response.status_code == 401


def test_create_and_get_manuscript(client):
    # 로그인한 사용자가 원고를 생성하면 201로 응답하고,
    # 생성된 id로 다시 조회했을 때 동일한 원고를 돌려받아야 한다.
    _signup_and_login(client)
    response = client.post(
        "/api/manuscripts", json={"topic": "FastAPI 학습", "concept": "TIL"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["topic"] == "FastAPI 학습"
    assert body["concept"] == "TIL"
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


def _create_version(db_session, manuscript_id: str, kind="draft", revision=1) -> str:
    version = ManuscriptVersion(
        manuscript_id=uuid.UUID(manuscript_id),
        kind=kind,
        revision=revision,
        storage_key=f"{kind}s/{uuid.uuid4()}.md",
    )
    db_session.add(version)
    db_session.commit()
    db_session.refresh(version)
    return str(version.id)


def test_finalize_manuscript_marks_version_and_status(client, db_session):
    _signup_and_login(client, login_id="finalizetester")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "탈고 대상", "concept": "TIL"}
    )
    manuscript_id = create_response.json()["id"]
    version_id = _create_version(db_session, manuscript_id)

    response = client.post(
        f"/api/manuscripts/{manuscript_id}/finalize", params={"version_id": version_id}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "finalized"

    version = db_session.get(ManuscriptVersion, uuid.UUID(version_id))
    assert version.is_finalized is True


def test_finalize_manuscript_unknown_version_returns_404(client):
    _signup_and_login(client, login_id="finalizetester2")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "탈고 대상2", "concept": "TIL"}
    )
    manuscript_id = create_response.json()["id"]

    response = client.post(
        f"/api/manuscripts/{manuscript_id}/finalize",
        params={"version_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


def test_delete_manuscript_soft_deletes_and_hides_from_list(client):
    # 삭제 요청 시 204를 반환하고, 목록/조회 API에서 더 이상 노출되지 않아야 한다.
    _signup_and_login(client, login_id="deletetester")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "삭제 대상", "concept": "TIL"}
    )
    manuscript_id = create_response.json()["id"]

    response = client.delete(f"/api/manuscripts/{manuscript_id}")
    assert response.status_code == 204

    assert client.get(f"/api/manuscripts/{manuscript_id}").status_code == 404
    list_ids = [m["id"] for m in client.get("/api/manuscripts").json()]
    assert manuscript_id not in list_ids


def test_delete_manuscript_requires_ownership(client, db_session):
    _signup_and_login(client, login_id="delowner")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "타인 원고", "concept": "TIL"}
    )
    manuscript_id = create_response.json()["id"]

    _signup_and_login(client, login_id="delother")
    response = client.delete(f"/api/manuscripts/{manuscript_id}")
    assert response.status_code == 404


def test_finalize_manuscript_other_users_version_returns_404(client, db_session):
    _signup_and_login(client, login_id="owner_user")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "소유자 원고", "concept": "TIL"}
    )
    manuscript_id = create_response.json()["id"]
    version_id = _create_version(db_session, manuscript_id)

    # 다른 사용자로 재로그인하면 쿠키가 교체된다.
    _signup_and_login(client, login_id="other_user")
    response = client.post(
        f"/api/manuscripts/{manuscript_id}/finalize", params={"version_id": version_id}
    )
    assert response.status_code == 404
