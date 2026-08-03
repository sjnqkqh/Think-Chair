from uuid import uuid4

import pytest

from app.research.evidence_index import ResearchEvidenceIndex
from app.research.retrieval import retrieve_evidence
from app.research.contracts import EvidenceRequest

pytestmark = pytest.mark.unit


def _index(tmp_path) -> ResearchEvidenceIndex:
    return ResearchEvidenceIndex(
        tmp_path / "chroma_db",
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )


def test_retrieve_evidence_returns_matching_public_chunk(tmp_path):
    evidence_index = _index(tmp_path)
    source_id = str(uuid4())
    evidence_index.store_source_chunks(
        scope="public",
        ids=["chunk-timeout"],
        documents=["기본 job timeout은 360분이다."],
        embeddings=[[1.0, 0.0, 0.0]],
        metadatas=[
            {
                "chunk_id": "chunk-timeout",
                "source_id": source_id,
                "canonical_url": "https://docs.example/timeout",
                "source_url": "https://docs.example/timeout",
                "title": "Timeout defaults",
                "language": "ko",
            }
        ],
    )

    result = retrieve_evidence(
        EvidenceRequest(
            user_id=uuid4(),
            manuscript_id=uuid4(),
            query="GitHub Actions timeout",
            limit=3,
        ),
        evidence_index=evidence_index,
        query_embedding=[1.0, 0.0, 0.0],
    )

    assert result.sufficiency.sufficient is True
    assert result.is_grounded is True
    assert result.items[0].chunk_id == "chunk-timeout"
    assert result.items[0].source_id == source_id
    assert result.items[0].url == "https://docs.example/timeout"
    assert "360분" in result.items[0].excerpt


def test_retrieve_evidence_excludes_other_users_private_chunks(tmp_path):
    evidence_index = _index(tmp_path)
    owner_user = uuid4()
    owner_manuscript = uuid4()
    other_user = uuid4()
    evidence_index.store_source_chunks(
        scope="private",
        ids=["chunk-private"],
        documents=["비공개 실험에서 지연이 절반으로 줄었다."],
        embeddings=[[1.0, 0.0, 0.0]],
        metadatas=[
            {
                "chunk_id": "chunk-private",
                "source_id": str(uuid4()),
                "canonical_url": "https://private.example/note",
                "source_url": "https://private.example/note",
                "title": "Private note",
                "language": "ko",
                "owner_user_id": str(other_user),
                "owner_manuscript_id": str(uuid4()),
            }
        ],
    )

    result = retrieve_evidence(
        EvidenceRequest(
            user_id=owner_user,
            manuscript_id=owner_manuscript,
            query="지연 개선",
            limit=3,
        ),
        evidence_index=evidence_index,
        query_embedding=[1.0, 0.0, 0.0],
    )

    assert result.items == []
    assert result.sufficiency.sufficient is False
    assert result.is_grounded is False
