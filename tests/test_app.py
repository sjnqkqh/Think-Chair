def test_health_check(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "online"
    assert "service" in response.json()


def test_chat_ui(client):
    response = client.get("/chat")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "규정 안내 헬퍼" in response.text
