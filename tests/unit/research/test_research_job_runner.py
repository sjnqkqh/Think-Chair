import json
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.manuscript import ConceptType, Manuscript, ManuscriptStatus
from app.models.research import ResearchJob, ResearchJobStatus, ResponseComparisonRecord
from app.models.user import User
from app.research.evidence_index import ResearchEvidenceIndex
from app.research.research_job_runner import run_research_job
from tests.db_setup import prepare_test_database

pytestmark = pytest.mark.unit


@pytest.fixture
def db_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    prepare_test_database(engine)
    return sessionmaker(bind=engine)


def _seed_job(session, *, claim="timeout이 60분이라고 했습니다."):
    user = User(login_id=f"u-{uuid4().hex[:8]}", password_hash="x", nickname="r")
    session.add(user)
    session.flush()
    manuscript = Manuscript(
        user_id=user.id,
        topic="timeout",
        concept=ConceptType.TECH_DEEPDIVE,
        status=ManuscriptStatus.DRAFTING,
    )
    session.add(manuscript)
    session.flush()
    job = ResearchJob(
        user_id=user.id,
        manuscript_id=manuscript.id,
        message_id=uuid4(),
        claim_or_query=claim,
        status=ResearchJobStatus.QUEUED,
    )
    session.add(job)
    session.commit()
    job_id =     job.id
    session.close()
    return job_id


def _store_three_relevant_urls(evidence_index: ResearchEvidenceIndex) -> None:
    """충분성 기준(관련 URL 3개)을 만족시키되, 인용 검증용 chunk-timeout은 그대로 둔다."""
    evidence_index.store_source_chunks(
        scope="public",
        ids=["chunk-timeout", "chunk-extra-1", "chunk-extra-2"],
        documents=[
            "기본 job timeout은 360분이다.",
            "다른 문서에서도 같은 기본값을 확인했다.",
            "세 번째 출처도 같은 기본값을 확인했다.",
        ],
        embeddings=[[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        metadatas=[
            {
                "chunk_id": "chunk-timeout",
                "source_id": "src-timeout",
                "canonical_url": "https://docs.example/timeout",
                "title": "Timeout",
                "language": "ko",
            },
            {
                "chunk_id": "chunk-extra-1",
                "source_id": "src-extra-1",
                "canonical_url": "https://docs.example/timeout-2",
                "title": "Timeout 2",
                "language": "ko",
            },
            {
                "chunk_id": "chunk-extra-2",
                "source_id": "src-extra-2",
                "canonical_url": "https://docs.example/timeout-3",
                "title": "Timeout 3",
                "language": "ko",
            },
        ],
    )


@pytest.mark.asyncio
async def test_run_research_job_completes_and_stores_comparison(db_factory, tmp_path):
    job_id = _seed_job(db_factory())

    evidence_index = ResearchEvidenceIndex(
        tmp_path / "chroma",
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )
    _store_three_relevant_urls(evidence_index)

    def generate_invoke(prompt: str) -> str:
        if "chunk_id" in prompt:
            return json.dumps(
                {
                    "body": "기본 timeout은 360분입니다. https://docs.example/timeout",
                    "citations": [
                        {
                            "source_id": "src-timeout",
                            "chunk_id": "chunk-timeout",
                            "url": "https://docs.example/timeout",
                        }
                    ],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "body": "정확한 기본값을 확인해 볼까요?",
                "cited_source_keys": [],
                "cited_urls": [],
            },
            ensure_ascii=False,
        )

    def judge_invoke(prompt: str) -> str:
        answer_a = prompt.split("[Answer A]", 1)[1].split("[Answer B]", 1)[0]
        grounded_is_a = "360분" in answer_a
        high, low = (90, 55) if grounded_is_a else (55, 90)
        return json.dumps(
            {
                "specificity": {"A": high, "B": low},
                "naturalness": {"A": 80, "B": 80},
                "accuracy": {"A": high, "B": low},
                "overall": {"A": high, "B": low},
                "reason": "근거 답이 수치를 보정한다.",
            },
            ensure_ascii=False,
        )

    await run_research_job(
        job_id=job_id,
        db_factory=db_factory,
        evidence_index=evidence_index,
        embed_query=lambda _: [1.0, 0.0, 0.0],
        generate_invoke=generate_invoke,
        judge_invoke=judge_invoke,
        generation_model="test-gen",
        judge_model="test-judge",
    )

    verify = db_factory()
    refreshed = verify.get(ResearchJob, job_id)
    record = (
        verify.query(ResponseComparisonRecord)
        .filter(ResponseComparisonRecord.research_job_id == job_id)
        .one()
    )

    assert refreshed.status == ResearchJobStatus.COMPLETED
    assert "360분" in record.grounded_body
    judgment = json.loads(record.judgment_json)
    assert judgment["overall_winner"] == "grounded"
    assert judgment["grounded_scores"]["overall"] == 90
    assert judgment["baseline_scores"]["overall"] == 55
    assert record.comparison_error is None
    verify.close()


@pytest.mark.asyncio
async def test_run_research_job_completes_without_evaluation(db_factory, tmp_path):
    job_id = _seed_job(db_factory())
    evidence_index = ResearchEvidenceIndex(
        tmp_path / "chroma-no-eval",
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )
    _store_three_relevant_urls(evidence_index)

    await run_research_job(
        job_id=job_id,
        db_factory=db_factory,
        evidence_index=evidence_index,
        embed_query=lambda _: [1.0, 0.0, 0.0],
    )

    verify = db_factory()
    refreshed = verify.get(ResearchJob, job_id)
    record_count = (
        verify.query(ResponseComparisonRecord)
        .filter(ResponseComparisonRecord.research_job_id == job_id)
        .count()
    )
    assert refreshed.status == ResearchJobStatus.COMPLETED
    assert record_count == 0
    verify.close()


@pytest.mark.asyncio
async def test_run_research_job_fails_when_web_research_yields_no_evidence(
    db_factory, tmp_path
):
    job_id = _seed_job(db_factory())
    evidence_index = ResearchEvidenceIndex(
        tmp_path / "chroma-empty",
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )

    async def web_research(**_kwargs):
        return "search_not_configured"

    await run_research_job(
        job_id=job_id,
        db_factory=db_factory,
        evidence_index=evidence_index,
        embed_query=lambda _: [0.0, 1.0, 0.0],
        web_research=web_research,
    )

    verify = db_factory()
    refreshed = verify.get(ResearchJob, job_id)
    assert refreshed.status == ResearchJobStatus.FAILED
    assert refreshed.terminal_error == "search_not_configured"
    verify.close()


@pytest.mark.asyncio
async def test_run_research_job_keeps_cancelled_status_at_finish(db_factory, tmp_path):
    job_id = _seed_job(db_factory())
    evidence_index = ResearchEvidenceIndex(
        tmp_path / "chroma-cancel",
        embedding_model="test-model",
        embedding_dimension=3,
        chunk_schema_version="test-schema",
    )
    evidence_index.store_source_chunks(
        scope="public",
        ids=["chunk-timeout"],
        documents=["기본 job timeout은 360분이다."],
        embeddings=[[1.0, 0.0, 0.0]],
        metadatas=[
            {
                "chunk_id": "chunk-timeout",
                "source_id": "src-timeout",
                "canonical_url": "https://docs.example/timeout",
                "title": "Timeout",
                "language": "ko",
            }
        ],
    )

    def embed_query(_query: str) -> list[float]:
        cancel_session = db_factory()
        cancelled = cancel_session.get(ResearchJob, job_id)
        cancelled.mark_cancelled()
        cancel_session.commit()
        cancel_session.close()
        return [1.0, 0.0, 0.0]

    await run_research_job(
        job_id=job_id,
        db_factory=db_factory,
        evidence_index=evidence_index,
        embed_query=embed_query,
        generate_invoke=lambda _p: "{}",
        judge_invoke=lambda _p: "{}",
    )

    verify = db_factory()
    refreshed = verify.get(ResearchJob, job_id)
    record_count = (
        verify.query(ResponseComparisonRecord)
        .filter(ResponseComparisonRecord.research_job_id == job_id)
        .count()
    )
    assert refreshed.status == ResearchJobStatus.CANCELLED
    assert record_count == 0
    verify.close()
