import pytest

from tests.helpers import signup

pytestmark = pytest.mark.integration


def test_put_llm_settings_updates_selection(client):
    signup(client, login_id="llm-settings-put")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "설정 API", "concept": "TIL"}
    )
    manuscript_id = create_response.json()["id"]

    response = client.put(
        f"/api/manuscripts/{manuscript_id}/llm-settings",
        json={
            "provider": "openai",
            "model": "gpt-5.6-sol",
            "effort": "low",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "provider": "openai",
        "model": "gpt-5.6-sol",
        "effort": "low",
    }


def test_put_llm_settings_rejects_unknown_effort(client):
    signup(client, login_id="llm-settings-bad-effort")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "설정 API", "concept": "TIL"}
    )
    manuscript_id = create_response.json()["id"]

    response = client.put(
        f"/api/manuscripts/{manuscript_id}/llm-settings",
        json={
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "effort": "ultra",
        },
    )

    assert response.status_code == 400


def test_workspace_page_includes_llm_settings(client):
    signup(client, login_id="llm-settings-workspace")
    create_response = client.post(
        "/api/manuscripts", json={"topic": "설정 페이지", "concept": "TIL"}
    )
    manuscript_id = create_response.json()["id"]

    response = client.get(f"/workspace/{manuscript_id}")

    assert response.status_code == 200
    assert "deepseek-v4-flash" in response.text
    assert "llm-settings-modal" in response.text
    assert "llm-settings-open" in response.text
