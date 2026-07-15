import json


def join_sse_chunks(body: str) -> str:
    """SSE 응답 본문에서 event: chunk 조각들의 content를 이어붙여 반환한다."""
    chunks = []
    for event in body.strip().split("\n\n"):
        if "\nevent: chunk\n" not in f"\n{event}\n":
            continue
        data = event.split("data: ", 1)[1]
        chunks.append(json.loads(data)["content"])
    return "".join(chunks)


def signup(client, login_id="tester", nickname="테스터"):
    """TestClient(동기)로 가입한다. signup이 즉시 쿠키를 발급하므로 로그인은 불필요."""
    return client.post(
        "/api/auth/signup",
        json={"login_id": login_id, "password": "password123", "nickname": nickname},
    )


async def signup_async(client, login_id, nickname="테스터"):
    """AsyncClient(e2e)로 가입한다."""
    return await client.post(
        "/api/auth/signup",
        json={"login_id": login_id, "password": "password123", "nickname": nickname},
    )
