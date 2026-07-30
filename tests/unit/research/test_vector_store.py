import pytest

from app.research.vector_store import (
    EmbeddingConfigurationMismatch,
    ResearchVectorStore,
)


def test_persists_vectors_and_reopens_compatible_collections(tmp_path):
    """같은 설정으로 Chroma를 다시 열어도 저장한 공개 벡터와 출처 정보가 유지되는지 검증한다."""
    store = ResearchVectorStore(
        tmp_path / "chroma_db",
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )
    store.upsert(
        scope="public",
        ids=["chunk-1"],
        documents=["근거 본문"],
        embeddings=[[1.0, 0.0, 0.0]],
        metadatas=[
            {
                "source_id": "source-1",
                "canonical_url": "https://example.com/source",
            }
        ],
    )

    reopened = ResearchVectorStore(
        tmp_path / "chroma_db",
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )

    assert reopened.count("public") == 1
    assert reopened.get("public")["metadatas"][0]["canonical_url"] == (
        "https://example.com/source"
    )


def test_rejects_collection_with_different_embedding_contract(tmp_path):
    """기존 컬렉션의 모델·차원·청킹 규칙이 다르면 벡터를 섞지 않고 거부하는지 검증한다."""
    ResearchVectorStore(
        tmp_path / "chroma_db",
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )

    with pytest.raises(EmbeddingConfigurationMismatch):
        ResearchVectorStore(
            tmp_path / "chroma_db",
            embedding_model="other-model",
            embedding_dimension=4,
            chunk_schema_version="other-schema",
        )
