from uuid import uuid4

import pytest

from app.research.evidence_index import ResearchEvidenceIndex
from app.research.retrieval import (
    MIN_DISTINCT_RELEVANT_URLS,
    MIN_RELEVANCE_SCORE,
    retrieve_evidence,
)
from app.research.contracts import EvidenceRequest

pytestmark = pytest.mark.unit


def _index(tmp_path) -> ResearchEvidenceIndex:
    return ResearchEvidenceIndex(
        f"sqlite:///{tmp_path / 'evidence.db'}",
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )


def _store_chunk(evidence_index, *, chunk_id, url, distance_embedding, document="본문"):
    evidence_index.store_source_chunks(
        scope="public",
        ids=[chunk_id],
        documents=[document],
        embeddings=[distance_embedding],
        metadatas=[
            {
                "chunk_id": chunk_id,
                "source_id": str(uuid4()),
                "canonical_url": url,
                "source_url": url,
                "title": "title",
                "language": "ko",
            }
        ],
    )


def test_single_relevant_chunk_is_not_sufficient(tmp_path):
    """무관한 자료가 없어도 관련 URL이 1개뿐이면 충분하지 않다."""
    evidence_index = _index(tmp_path)
    _store_chunk(
        evidence_index,
        chunk_id="chunk-timeout",
        url="https://docs.example/timeout",
        distance_embedding=[1.0, 0.0, 0.0],
        document="기본 job timeout은 360분이다.",
    )

    result = retrieve_evidence(
        EvidenceRequest(
            user_id=uuid4(),
            manuscript_id=uuid4(),
            query="GitHub Actions timeout",
            limit=5,
        ),
        evidence_index=evidence_index,
        query_embedding=[1.0, 0.0, 0.0],
    )

    assert result.sufficiency.sufficient is False
    assert result.is_grounded is False
    assert result.items[0].chunk_id == "chunk-timeout"
    assert "360분" in result.items[0].excerpt


def test_three_distinct_relevant_urls_are_sufficient(tmp_path):
    evidence_index = _index(tmp_path)
    for index in range(3):
        _store_chunk(
            evidence_index,
            chunk_id=f"chunk-{index}",
            url=f"https://docs.example/{index}",
            distance_embedding=[1.0, 0.0, 0.0],
        )

    result = retrieve_evidence(
        EvidenceRequest(
            user_id=uuid4(),
            manuscript_id=uuid4(),
            query="timeout",
            limit=5,
        ),
        evidence_index=evidence_index,
        query_embedding=[1.0, 0.0, 0.0],
    )

    assert result.sufficiency.sufficient is True
    assert result.is_grounded is True
    assert len(result.sufficiency.supporting_chunk_ids) == 3


def test_many_chunks_from_same_url_count_as_one_source(tmp_path):
    """같은 URL에서 조각이 많아도 출처 1개로 센다."""
    evidence_index = _index(tmp_path)
    for index in range(5):
        _store_chunk(
            evidence_index,
            chunk_id=f"chunk-{index}",
            url="https://docs.example/only-source",
            distance_embedding=[1.0, 0.0, 0.0],
        )

    result = retrieve_evidence(
        EvidenceRequest(
            user_id=uuid4(),
            manuscript_id=uuid4(),
            query="timeout",
            limit=5,
        ),
        evidence_index=evidence_index,
        query_embedding=[1.0, 0.0, 0.0],
    )

    assert result.sufficiency.sufficient is False
    assert result.sufficiency.reason_code == "insufficient_distinct_urls"


def test_score_below_threshold_is_not_relevant(tmp_path):
    """score = 1/(1+distance)가 0.45 미만이면 관련 자료로 세지 않는다."""
    evidence_index = _index(tmp_path)
    # distance가 커서 score < 0.45가 되도록, 쿼리와 먼 임베딩을 사용한다.
    for index in range(3):
        _store_chunk(
            evidence_index,
            chunk_id=f"chunk-{index}",
            url=f"https://docs.example/{index}",
            distance_embedding=[0.0, 1.0, 0.0],
        )

    result = retrieve_evidence(
        EvidenceRequest(
            user_id=uuid4(),
            manuscript_id=uuid4(),
            query="timeout",
            limit=5,
        ),
        evidence_index=evidence_index,
        query_embedding=[1.0, 0.0, 0.0],
    )

    assert all(item.score < MIN_RELEVANCE_SCORE for item in result.items)
    assert result.sufficiency.sufficient is False
    assert result.sufficiency.reason_code == "no_matching_chunks"
    assert result.sufficiency.supporting_chunk_ids == []


def test_min_distinct_relevant_urls_constant_is_three():
    assert MIN_DISTINCT_RELEVANT_URLS == 3


class _FixedDistanceIndex:
    """distance를 그대로 지정해 점수 경계를 정밀하게 테스트하기 위한 fake."""

    def __init__(self, hits: list[dict]):
        self._hits = hits

    def query_chunks(self, *, scope, query_embedding, limit, where=None):
        return self._hits if scope == "public" else []


def _fixed_hit(chunk_id: str, url: str, distance: float) -> dict:
    return {
        "id": chunk_id,
        "document": "본문",
        "metadata": {"chunk_id": chunk_id, "canonical_url": url, "source_id": "s"},
        "distance": distance,
    }


def test_score_boundary_at_min_relevance_threshold():
    """score = 1/(1+distance)가 0.45 미만이면 관련 자료에서 제외한다."""
    boundary_distance = 1.0 / MIN_RELEVANCE_SCORE - 1.0
    # 부동소수 오차로 경계값이 0.45를 밑돌 수 있어, 위/아래로 여유를 둔다.
    above_threshold_distance = boundary_distance - 0.01
    below_threshold_distance = boundary_distance + 0.01

    evidence_index = _FixedDistanceIndex(
        [
            _fixed_hit("below", "https://example/below", below_threshold_distance),
            _fixed_hit("at-1", "https://example/at-1", above_threshold_distance),
            _fixed_hit("at-2", "https://example/at-2", above_threshold_distance),
            _fixed_hit("at-3", "https://example/at-3", above_threshold_distance),
        ]
    )

    result = retrieve_evidence(
        EvidenceRequest(user_id=uuid4(), manuscript_id=uuid4(), query="q", limit=5),
        evidence_index=evidence_index,
        query_embedding=[0.0],
    )

    relevant_urls = {item.url for item in result.items if item.score >= MIN_RELEVANCE_SCORE}
    assert "https://example/below" not in relevant_urls
    assert len(relevant_urls) == 3
    assert result.sufficiency.sufficient is True


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
