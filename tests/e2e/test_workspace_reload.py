import pytest
from httpx import ASGITransport, AsyncClient

from main import app as fastapi_app
from tests.helpers import signup_async

pytestmark = pytest.mark.e2e


async def test_workspace_detail_reload_with_history_renders_messages(chat_app_state):
    # 회귀 테스트: _chat_center.html의 for 루프 변수명이 _message.html이 기대하는
    # "message"와 달라 대화 이력이 있는 상태로 새로고침하면 500이 발생했었다.
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        await signup_async(client, "workspacereload")
        create_res = await client.post(
            "/api/manuscripts", json={"topic": "재현", "concept": "TIL"}
        )
        manuscript_id = create_res.json()["id"]

        msg_res = await client.post(
            f"/api/chat/{manuscript_id}/message", data={"content": "안녕하세요"}
        )
        assert msg_res.status_code == 200

        reload_res = await client.get(f"/workspace/{manuscript_id}")
        assert reload_res.status_code == 200
        assert "안녕하세요" in reload_res.text
        assert "테스트 응답입니다" in reload_res.text
