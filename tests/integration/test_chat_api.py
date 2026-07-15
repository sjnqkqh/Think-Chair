import pytest

from tests.helpers import join_sse_chunks, signup

pytestmark = pytest.mark.integration


def test_send_message_requires_auth(client):
    response = client.post(
        "/api/chat/11111111-1111-1111-1111-111111111111/message",
        data={"content": "안녕하세요"},
    )
    assert response.status_code == 401


def test_send_message_returns_ai_response(client, chat_app_state):
    signup(client, login_id="chattester")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "FastAPI 학습", "concept": "TIL"}
    )
    manuscript_id = create_response.json()["id"]

    response = client.post(
        f"/api/chat/{manuscript_id}/message", data={"content": "안녕하세요"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert join_sse_chunks(response.text) == "테스트 응답입니다."
