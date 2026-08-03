import json
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.database import Base
from app.models.manuscript import ConceptType, Manuscript, ManuscriptStatus
from app.models.research import ResearchJob, ResearchJobStatus, ResponseComparisonRecord
from app.models.user import User
from app.research.evidence_index import ResearchEvidenceIndex
from app.research.research_job_runner import run_research_job
from app.research.schema_ensure import ensure_research_schema

pytestmark = pytest.mark.unit


@pytest.fixture
def db_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    ensure_research_schema(engine)
    return sessionmaker(bind=engine)


@pytest.mark.asyncio
async def test_run_research_job_stores_baseline_grounded_comparison(db_factory, tmp_path):
    session = db_factory()
    user = User(login_id="research-user", password_hash="x", nickname="r")
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
        claim_or_query="timeout이 60분이라고 했습니다.",
        status=ResearchJobStatus.QUEUED,
    )
    session.add(job)
    session.commit()
    job_id = job.id
    session.close()

    evidence_index = ResearchEvidenceIndex(
        tmp_path / "chroma",
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
        winner = "A" if grounded_is_a else "B"
        return json.dumps(
            {
                "specificity_winner": winner,
                "naturalness_winner": "tie",
                "accuracy_winner": winner,
                "overall_winner": winner,
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
    assert "https://docs.example/timeout" in record.grounded_body
    assert record.overall_winner == "grounded"
    assert record.comparison_error is None
    verify.close()
