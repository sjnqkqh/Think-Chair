def test_history_list_endpoints(client):
    assert client.get("/history/uploads").status_code == 200
    assert client.get("/history/evaluations").status_code == 200


def test_delete_upload_history_success(client, monkeypatch):
    from app.services.document import DocumentService

    monkeypatch.setattr(DocumentService, "delete_document_and_embeddings", lambda db, history_id: "test_rules.txt")

    response = client.delete("/history/uploads/1")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert "test_rules.txt" in response.json()["message"]


def test_delete_upload_history_not_found(client, monkeypatch):
    from app.services.document import DocumentService
    from fastapi import HTTPException

    monkeypatch.setattr(DocumentService, "delete_document_and_embeddings", lambda db, history_id: (_ for _ in ()).throw(HTTPException(status_code=404)))

    assert client.delete("/history/uploads/99999").status_code == 404
