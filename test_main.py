import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from main import app
from app.api.endpoints import get_rag_service, get_evaluator_service
from app.services.rag import RagService
from app.services.evaluator import EvaluatorService

client = TestClient(app)
mock_service = MagicMock(spec=RagService)
mock_evaluator = MagicMock(spec=EvaluatorService)


@pytest.fixture(autouse=True)
def setup_dependency_overrides():
    app.dependency_overrides[get_rag_service] = lambda: mock_service
    app.dependency_overrides[get_evaluator_service] = lambda: mock_evaluator
    yield
    mock_service.reset_mock()
    mock_evaluator.reset_mock()
    app.dependency_overrides.clear()


def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "online"
    assert "service" in response.json()


def test_index_endpoint_success():
    mock_service.index_documents.return_value = 34

    response = client.post("/index")

    assert response.status_code == 200
    assert response.json() == {"status": "success", "indexed_count": 34}
    mock_service.index_documents.assert_called_once()


def test_index_endpoint_file_not_found():
    mock_service.index_documents.side_effect = FileNotFoundError(
        "chunks.json not found"
    )

    response = client.post("/index")

    assert response.status_code == 404
    assert "detail" in response.json()


def test_query_endpoint():
    mock_service.query.return_value = {
        "answer": "지각 3회 누적 시 1일 결석 처리됩니다.",
        "contexts": ["지각·조퇴·외출 3회 누적 시 1일 결석 처리"],
        "metadatas": [{"id": 3, "char_count": 50}],
    }

    payload = {
        "question": "지각 3번 하면 어떻게 되나요?",
        "top_k": 3,
        "session_id": "test-session-id"
    }
    response = client.post("/query", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "지각 3회 누적 시 1일 결석 처리됩니다."
    assert len(data["contexts"]) == 1
    assert data["contexts"][0] == "지각·조퇴·외출 3회 누적 시 1일 결석 처리"
    assert data["metadatas"][0]["id"] == 3

    mock_service.query.assert_called_once_with("지각 3번 하면 어떻게 되나요?", "test-session-id", 3)


def test_query_stream_endpoint():
    mock_chunk_1 = MagicMock()
    mock_chunk_1.text = "지각"
    mock_chunk_2 = MagicMock()
    mock_chunk_2.text = " 3회 누적"

    mock_service.query_stream.return_value = (
        [mock_chunk_1, mock_chunk_2],
        ["참조 문서 1"],
        [{"id": 3}],
    )

    payload = {
        "question": "지각 3회?",
        "top_k": 2,
        "session_id": "test-session-id"
    }

    with client.stream("POST", "/query/stream", json=payload) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        lines = [line for line in response.iter_lines() if line]

        assert "event: metadata" in lines[0]
        meta_data = json.loads(lines[1].replace("data: ", ""))
        assert meta_data["contexts"] == ["참조 문서 1"]
        assert meta_data["metadatas"] == [{"id": 3}]

        assert "data: 지각" in lines[2]
        assert "data:  3회 누적" in lines[3]

        mock_service.query_stream.assert_called_once_with("지각 3회?", "test-session-id", 2)


def test_chat_ui_endpoint():
    response = client.get("/chat")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "규정 안내 헬퍼" in response.text


def test_upload_endpoint_success(monkeypatch):
    from app.services.chunking import ChunkingService
    from langchain_core.documents import Document

    monkeypatch.setattr(ChunkingService, "extract_text_from_file", lambda c, f: "텍스트 추출 내용")
    monkeypatch.setattr(ChunkingService, "split_document", lambda t, s, f: [Document(page_content="청크")])
    monkeypatch.setattr(ChunkingService, "get_collection_name_for_strategy", lambda s: "mock_collection")

    from app.core.vectorstore import VectorStoreManager
    monkeypatch.setattr(VectorStoreManager, "delete_existing_documents", lambda self, ids, collection_name: None)
    monkeypatch.setattr(VectorStoreManager, "add_documents_batch", lambda self, docs, ids, collection_name: None)

    strategies_payload = json.dumps([{"name": "recursive", "chunk_size": 500, "chunk_overlap": 50}])

    response = client.post(
        "/upload",
        files={"file": ("rules.txt", b"dummy content", "text/plain")},
        data={"strategies": strategies_payload}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["filename"] == "rules.txt"
    assert "mock_collection" in data["strategies_applied"]
    assert data["chunks_count"]["mock_collection"] == 1


def test_eval_run_endpoint_success():
    mock_evaluator.run_eval_for_strategy.return_value = {
        "answer": "지각 3회 시 결석 처리됩니다.",
        "contexts": ["지각 3회 결석"],
        "scores": {
            "faithfulness": {"score": 5, "reason": "사실 기반"},
            "relevance": {"score": 5, "reason": "질문에 답변"},
            "precision": {"score": 5, "reason": "정확한 맥락"}
        }
    }

    payload = {
        "question": "지각 규정은?",
        "ground_truth": "지각 3회는 결석 1일",
        "strategies": [{"name": "recursive", "chunk_size": 500, "chunk_overlap": 50}],
        "top_k": 3
    }

    response = client.post("/eval/run", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "지각 규정은?"
    assert len(data["results"]) == 1
    res = data["results"][0]
    assert "recursive" in res["strategy"]
    assert res["scores"]["faithfulness"]["score"] == 5
    mock_evaluator.run_eval_for_strategy.assert_called_once()

