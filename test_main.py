import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.endpoints.query import get_rag_service
from app.api.endpoints.evaluation import get_evaluator_service
from app.core.database import get_database_session, Base
from app.models.history import UploadHistory
from app.services.evaluator import EvaluatorService
from app.services.rag import RagService
from main import app as fastapi_app

# Setup in-memory database with StaticPool for testing
test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)

client = TestClient(fastapi_app)
mock_service = MagicMock(spec=RagService)
mock_evaluator = MagicMock(spec=EvaluatorService)


@pytest.fixture(autouse=True)
def setup_dependency_overrides(monkeypatch):
    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_rag_service] = lambda: mock_service
    fastapi_app.dependency_overrides[get_evaluator_service] = lambda: mock_evaluator
    fastapi_app.dependency_overrides[get_database_session] = override_get_db
    
    import app.api.endpoints.document
    import app.api.endpoints.evaluation
    import app.api.endpoints.history
    monkeypatch.setattr(app.api.endpoints.document, "get_database_session", override_get_db)
    monkeypatch.setattr(app.api.endpoints.evaluation, "get_database_session", override_get_db)
    monkeypatch.setattr(app.api.endpoints.history, "get_database_session", override_get_db)
    
    yield
    mock_service.reset_mock()
    mock_evaluator.reset_mock()
    fastapi_app.dependency_overrides.clear()


def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "online"
    assert "service" in response.json()


def test_query_endpoint():
    mock_service.query.return_value = {
        "answer": "지각 3회 누적 시 1일 결석 처리됩니다.",
        "contexts": ["지각·조퇴·외출 3회 누적 시 1일 결석 처리"],
        "metadatas": [{"id": 3, "char_count": 50}],
    }

    payload = {
        "question": "지각 3번 하면 어떻게 되나요?",
        "top_k": 3,
        "session_id": "test-session-id",
    }
    response = client.post("/query", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "지각 3회 누적 시 1일 결석 처리됩니다."
    assert len(data["contexts"]) == 1
    assert data["contexts"][0] == "지각·조퇴·외출 3회 누적 시 1일 결석 처리"
    assert data["metadatas"][0]["id"] == 3

    mock_service.query.assert_called_once_with(
        "지각 3번 하면 어떻게 되나요?", "test-session-id", 3
    )


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

    payload = {"question": "지각 3회?", "top_k": 2, "session_id": "test-session-id"}

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

        mock_service.query_stream.assert_called_once_with(
            "지각 3회?", "test-session-id", 2
        )


def test_chat_ui_endpoint():
    response = client.get("/chat")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "규정 안내 헬퍼" in response.text


def test_upload_endpoint_success(monkeypatch):
    from app.services.chunking import ChunkingService
    from langchain_core.documents import Document

    monkeypatch.setattr(
        ChunkingService, "extract_text_from_file", lambda c, f: "텍스트 추출 내용"
    )
    monkeypatch.setattr(
        ChunkingService,
        "split_document",
        lambda t, s, f: [Document(page_content="청크")],
    )
    monkeypatch.setattr(
        ChunkingService, "get_collection_name_for_strategy", lambda s: "mock_collection"
    )

    from app.core.vectorstore import VectorStoreManager

    monkeypatch.setattr(
        VectorStoreManager,
        "delete_existing_documents",
        lambda self, ids, collection_name: None,
    )
    monkeypatch.setattr(
        VectorStoreManager,
        "add_documents_batch",
        lambda self, docs, ids, collection_name: None,
    )

    strategies_payload = json.dumps(
        [{"name": "recursive", "chunk_size": 500, "chunk_overlap": 50}]
    )

    response = client.post(
        "/upload",
        files={"file": ("rules.txt", b"dummy content", "text/plain")},
        data={"strategies": strategies_payload},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["filename"] == "rules.txt"
    assert "history_id" in data
    assert "background" in data["message"]

    history_id = data["history_id"]
    status_resp = client.get(f"/upload/status/{history_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "completed"
    assert "mock_collection" in status_data["strategies_applied"]
    assert status_data["chunks_count"]["mock_collection"] == 1


def test_eval_run_endpoint_success():
    async def mock_run_batch(*args, **kwargs):
        return [
            {
                "strategy": "recursive (s=500, o=50)",
                "collection_name": "rag_recursive_500_50",
                "answer": "지각 3회 시 결석 처리됩니다.",
                "contexts": ["지각 3회 결석"],
                "scores": {
                    "faithfulness": {"score": 5, "reason": "사실 기반"},
                    "relevance": {"score": 5, "reason": "질문에 답변"},
                    "precision": {"score": 5, "reason": "정확한 맥락"},
                },
            }
        ]
    mock_evaluator.run_batch_evaluation = mock_run_batch

    payload = {
        "question": "지각 규정은?",
        "ground_truth": "지각 3회는 결석 1일",
        "strategies": [{"name": "recursive", "chunk_size": 500, "chunk_overlap": 50}],
        "top_k": 3,
    }

    response = client.post("/evaluation/run", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "지각 규정은?"
    assert len(data["results"]) == 1
    result_item = data["results"][0]
    assert "recursive" in result_item["strategy"]
    assert result_item["scores"]["faithfulness"]["score"] == 5


def test_eval_run_json_endpoint_success():
    async def mock_run_json_dataset(*args, **kwargs):
        summaries = [
            {
                "strategy": "recursive (s=500, o=50)",
                "faithfulness_avg": 5.0,
                "relevance_avg": 5.0,
                "precision_avg": 5.0,
                "recall_avg": 0.0,
                "completeness_avg": 0.0,
                "noise_ratio_avg": 0.0,
                "coverage_rate_avg": 0.0,
                "gt_match_rate_avg": 0.0,
                "avg_chunk_length_avg": 0.0,
            }
        ]
        evaluations = [
            {
                "id": 1,
                "question": "지각 규정은?",
                "ground_truth": "지각 3회는 결석 1일",
                "results": [
                    {
                        "strategy": "recursive (s=500, o=50)",
                        "collection_name": "rag_recursive_500_50",
                        "answer": "지각 3회 시 결석 처리됩니다.",
                        "contexts": ["지각 3회 결석"],
                        "scores": {
                            "faithfulness": {"score": 5, "reason": "사실 기반"},
                            "relevance": {"score": 5, "reason": "질문에 답변"},
                            "precision": {"score": 5, "reason": "정확한 맥락"},
                        },
                    }
                ]
            }
        ]
        return summaries, evaluations
    mock_evaluator.run_json_dataset_evaluation = mock_run_json_dataset

    payload = {
        "qa_pairs": [
            {
                "id": 1,
                "type": "A",
                "section": "섹션",
                "retrieval_hint": "힌트",
                "question": "지각 규정은?",
                "answer": "지각 3회는 결석 1일"
            }
        ],
        "strategies": [{"name": "recursive", "chunk_size": 500, "chunk_overlap": 50}],
        "top_k": 3,
    }

    response = client.post("/evaluation/run-json", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert len(data["summaries"]) == 1
    assert data["summaries"][0]["faithfulness_avg"] == 5.0
    assert len(data["evaluations"]) == 1
    assert data["evaluations"][0]["question"] == "지각 규정은?"


def test_history_endpoints():
    # 1. Check initially empty or containing entries
    resp_upload = client.get("/history/uploads")
    assert resp_upload.status_code == 200

    resp_eval = client.get("/history/evaluations")
    assert resp_eval.status_code == 200


def test_delete_upload_history_success(monkeypatch):
    db = TestSessionLocal()
    history = UploadHistory(
        filename="test_rules.txt",
        status="completed",
        strategies_applied=json.dumps(["mock_collection"]),
        chunks_count=json.dumps({"mock_collection": 1}),
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    history_id = history.id
    db.close()

    from app.core.vectorstore import VectorStoreManager
    monkeypatch.setattr(
        VectorStoreManager,
        "delete_existing_documents",
        lambda self, ids, collection_name: None,
    )

    response = client.delete(f"/history/uploads/{history_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "test_rules.txt" in data["message"]

    db = TestSessionLocal()
    record = db.query(UploadHistory).filter(UploadHistory.id == history_id).first()
    assert record is None
    db.close()


def test_delete_upload_history_not_found():
    response = client.delete("/history/uploads/99999")
    assert response.status_code == 404
