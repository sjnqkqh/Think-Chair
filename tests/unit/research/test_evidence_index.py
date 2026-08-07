"""조사 근거 벡터 인덱스 단위 테스트."""

import pytest

from app.research.evidence_index import (
    EvidenceIndexContractMismatch,
    ResearchEvidenceIndex,
)


def _url(tmp_path, name: str = "evidence.db") -> str:
    return f"sqlite:///{tmp_path / name}"


def test_persists_vectors_and_reopens_compatible_collections(tmp_path):
    """같은 설정으로 인덱스를 다시 열어도 저장한 공개 벡터와 출처 정보가 유지되는지 검증한다."""
    url = _url(tmp_path)
    evidence_index = ResearchEvidenceIndex(
        url,
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )
    evidence_index.store_source_chunks(
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

    reopened = ResearchEvidenceIndex(
        url,
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )

    assert reopened.count_chunks("public") == 1
    assert reopened.list_metadatas("public")[0]["canonical_url"] == (
        "https://example.com/source"
    )


def test_rejects_collection_with_different_embedding_contract(tmp_path):
    """기존 컬렉션의 모델·차원·청킹 규칙이 다르면 벡터를 섞지 않고 거부하는지 검증한다."""
    url = _url(tmp_path)
    ResearchEvidenceIndex(
        url,
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )

    with pytest.raises(EvidenceIndexContractMismatch):
        ResearchEvidenceIndex(
            url,
            embedding_model="other-model",
            embedding_dimension=4,
            chunk_schema_version="other-schema",
        )
