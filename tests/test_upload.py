import json


def test_upload_success(client, monkeypatch):
    from app.services.chunking import ChunkingService
    from app.core.vectorstore import VectorStoreManager
    from app.services.document import DocumentService
    from langchain_core.documents import Document

    monkeypatch.setattr(ChunkingService, "extract_text_from_file", lambda c, f: "텍스트")
    monkeypatch.setattr(ChunkingService, "split_document", lambda t, s, f: [Document(page_content="청크")])
    monkeypatch.setattr(ChunkingService, "get_collection_name_for_strategy", lambda s: "mock_collection")
    monkeypatch.setattr(VectorStoreManager, "delete_existing_documents", lambda self, ids, col: None)
    monkeypatch.setattr(VectorStoreManager, "add_documents_batch", lambda self, docs, ids, col: None)
    # background task calls next(get_database_session()) directly — patch at the service layer
    original_process = DocumentService.process_upload_task

    def mock_process(db, history_id, file_bytes, filename, strategy_list):
        from app.models.history import UploadHistory
        import json as _json
        record = db.query(UploadHistory).filter(UploadHistory.id == history_id).first()
        if record:
            record.status = "completed"
            record.strategies_applied = _json.dumps(["mock_collection"])
            record.chunks_count = _json.dumps({"mock_collection": 1})
            db.commit()

    monkeypatch.setattr(DocumentService, "process_upload_task", staticmethod(mock_process))

    response = client.post(
        "/upload",
        files={"file": ("rules.txt", b"dummy", "text/plain")},
        data={"strategies": json.dumps([{"name": "recursive", "chunk_size": 500, "chunk_overlap": 50}])},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["filename"] == "rules.txt"
    assert "history_id" in data

    status = client.get(f"/upload/status/{data['history_id']}")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert "mock_collection" in status.json()["strategies_applied"]
    assert status.json()["chunks_count"]["mock_collection"] == 1
