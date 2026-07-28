import datetime
import uuid

import pytest

from app.models.manuscript import Manuscript, ManuscriptVersion
from app.repositories import chat_repo
from tests.helpers import signup

pytestmark = pytest.mark.integration


def test_workspace_root_requires_auth(client):
    response = client.get("/workspace", follow_redirects=False)
    assert response.status_code == 303


def test_workspace_detail_requires_auth(client):
    response = client.get(f"/workspace/{uuid.uuid4()}", follow_redirects=False)
    assert response.status_code == 303


def test_workspace_root_renders_new_manuscript_button(client):
    # 로그인한 사용자에게 워크스페이스 홈이 열리고, 새 원고 진입점과 인증 상태 요소가 노출되어야 한다.
    signup(client, login_id="workspacetester")
    response = client.get("/workspace")
    assert response.status_code == 200
    assert "새 원고" in response.text
    assert "로그아웃" in response.text
    assert "답을 대신 내놓는 AI가 아니라" in response.text
    assert "concept: '딥다이브'" in response.text
    assert 'x-model="concept"' in response.text
    assert ':disabled="concept !== \'수업 자료\'"' in response.text


def test_workspace_detail_renders_version_download_label(client, db_session):
    signup(client, login_id=f"workspaceversion-{uuid.uuid4()}")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "버전 표시", "concept": "TIL"}
    )
    manuscript_id = uuid.UUID(create_response.json()["id"])
    db_session.add_all(
        [
            ManuscriptVersion(
                manuscript_id=manuscript_id,
                kind="outline",
                revision=1,
                storage_key="outlines/test.md",
                created_at=datetime.datetime(2026, 7, 8, 0, 6),
            ),
            ManuscriptVersion(
                manuscript_id=manuscript_id,
                kind="document",
                revision=1,
                storage_key="documents/test.md",
                created_at=datetime.datetime(2026, 7, 8, 0, 7),
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/workspace/{manuscript_id}")
    assert response.status_code == 200
    assert "개요 1" in response.text
    assert "문서 1" in response.text
    assert "버전 1" not in response.text
    assert 'class="text-sm text-[#787671]">(09:07)</span>' in response.text
    assert "[다운로드]" in response.text
    assert "document v1" not in response.text


def test_workspace_detail_renders_persisted_chat_messages(client, db_session):
    signup(client, login_id=f"workspacehistory-{uuid.uuid4()}")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "대화 표시", "concept": "TIL"}
    )
    manuscript_id = uuid.UUID(create_response.json()["id"])
    manuscript = db_session.get(Manuscript, manuscript_id)
    chat_repo.create_message(db_session, manuscript, "user", "저장된 질문", None)
    chat_repo.create_message(
        db_session, manuscript, "assistant", "저장된 답변", "opening"
    )
    response = client.get(f"/workspace/{manuscript_id}")

    assert response.status_code == 200
    assert "저장된 질문" in response.text
    assert "저장된 답변" in response.text
    assert "message-human" in response.text


def test_workspace_detail_without_persisted_messages_renders_empty_history(client):
    signup(client, login_id=f"workspacelegacy-{uuid.uuid4()}")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "기존 대화", "concept": "TIL"}
    )
    manuscript_id = uuid.UUID(create_response.json()["id"])

    response = client.get(f"/workspace/{manuscript_id}")

    assert response.status_code == 200
    assert 'class="message ' not in response.text


def test_workspace_detail_unknown_manuscript_returns_404(client):
    signup(client, login_id="workspacetester2")
    response = client.get(f"/workspace/{uuid.uuid4()}")
    assert response.status_code == 404
