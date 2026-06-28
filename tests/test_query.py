def test_query_endpoint(client, mock_rag):
    mock_rag.query.return_value = {
        "answer": "지각 3회 누적 시 1일 결석 처리됩니다.",
        "contexts": ["지각·조퇴·외출 3회 누적 시 1일 결석 처리"],
        "metadatas": [{"id": 3, "char_count": 50}],
    }

    response = client.post(
        "/query",
        json={"question": "지각 3번 하면 어떻게 되나요?", "top_k": 3, "session_id": "test-session"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "지각 3회 누적 시 1일 결석 처리됩니다."
    assert data["contexts"] == ["지각·조퇴·외출 3회 누적 시 1일 결석 처리"]
    assert data["metadatas"][0]["id"] == 3
    mock_rag.query.assert_called_once_with("지각 3번 하면 어떻게 되나요?", "test-session", 3)


def test_query_stream_endpoint(client, mock_rag):
    from unittest.mock import MagicMock

    chunk1, chunk2 = MagicMock(), MagicMock()
    chunk1.text, chunk2.text = "지각", " 3회 누적"
    mock_rag.query_stream.return_value = ([chunk1, chunk2], ["참조 문서 1"], [{"id": 3}])

    with client.stream("POST", "/query/stream", json={"question": "지각 3회?", "top_k": 2, "session_id": "s1"}) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        lines = [line for line in response.iter_lines() if line]
        assert "event: metadata" in lines[0]

        import json
        meta = json.loads(lines[1].replace("data: ", ""))
        assert meta["contexts"] == ["참조 문서 1"]
        assert meta["metadatas"] == [{"id": 3}]
        assert "data: 지각" in lines[2]
        assert "data:  3회 누적" in lines[3]

    mock_rag.query_stream.assert_called_once_with("지각 3회?", "s1", 2)
