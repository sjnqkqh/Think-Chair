"""원고별 조사 사용량(research_usage)과 job 상한 검증."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.database import Base
from app.core.exceptions import ConflictError
from app.models.manuscript import ConceptType, Manuscript, ManuscriptStatus
from app.models.research import ResearchUsage
from app.models.user import User
from app.repositories import research_repo
from app.research.schema_ensure import ensure_research_schema
from app.services.research_job_service import (
    MAX_RESEARCH_JOBS_PER_MANUSCRIPT,
    create_or_get_research_job,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'usage.db'}")
    Base.metadata.create_all(bind=engine)
    ensure_research_schema(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_user_and_manuscript(db_session):
    user = User(login_id=f"u-{uuid4().hex[:8]}", password_hash="x", nickname="n")
    db_session.add(user)
    db_session.flush()
    manuscript = Manuscript(
        user_id=user.id,
        topic="usage",
        concept=ConceptType.TECH_DEEPDIVE,
        status=ManuscriptStatus.DRAFTING,
    )
    db_session.add(manuscript)
    db_session.commit()
    return user, manuscript


def test_increment_job_count_creates_usage_row(db_session):
    user, manuscript = _seed_user_and_manuscript(db_session)

    usage = research_repo.increment_research_job_count(
        db_session,
        user_id=user.id,
        manuscript_id=manuscript.id,
    )
    db_session.commit()

    assert usage.job_count == 1
    assert usage.search_count == 0
    stored = (
        db_session.query(ResearchUsage)
        .filter(ResearchUsage.manuscript_id == manuscript.id)
        .one()
    )
    assert stored.job_count == 1


def test_create_research_job_rejects_when_manuscript_job_limit_reached(db_session):
    user, manuscript = _seed_user_and_manuscript(db_session)
    started = []

    class _Background:
        def start(self, coroutine):
            started.append(coroutine)
            coroutine.close()

    background = _Background()

    def run_job(job_id):
        async def _run():
            started.append(job_id)

        return _run()

    for _ in range(MAX_RESEARCH_JOBS_PER_MANUSCRIPT):
        job, created = create_or_get_research_job(
            db_session,
            user_id=user.id,
            manuscript_id=manuscript.id,
            message_id=uuid4(),
            claim_or_query="일반론 주장",
            background_tasks=background,
            run_job=run_job,
            concept=manuscript.concept,
        )
        assert created is True
        assert job.id is not None

    usage = (
        db_session.query(ResearchUsage)
        .filter(ResearchUsage.manuscript_id == manuscript.id)
        .one()
    )
    assert usage.job_count == MAX_RESEARCH_JOBS_PER_MANUSCRIPT

    with pytest.raises(ConflictError, match="최대 5"):
        create_or_get_research_job(
            db_session,
            user_id=user.id,
            manuscript_id=manuscript.id,
            message_id=uuid4(),
            claim_or_query="여섯 번째 조사",
            background_tasks=background,
            run_job=run_job,
            concept=manuscript.concept,
        )

    assert usage.job_count == MAX_RESEARCH_JOBS_PER_MANUSCRIPT


def test_existing_message_job_does_not_consume_extra_quota(db_session):
    user, manuscript = _seed_user_and_manuscript(db_session)
    message_id = uuid4()

    class _Background:
        def start(self, coroutine):
            coroutine.close()

    background = _Background()

    def run_job(_job_id):
        async def _run():
            return None

        return _run()

    first, created_first = create_or_get_research_job(
        db_session,
        user_id=user.id,
        manuscript_id=manuscript.id,
        message_id=message_id,
        claim_or_query="같은 메시지",
        background_tasks=background,
        run_job=run_job,
        concept=manuscript.concept,
    )
    second, created_second = create_or_get_research_job(
        db_session,
        user_id=user.id,
        manuscript_id=manuscript.id,
        message_id=message_id,
        claim_or_query="같은 메시지",
        background_tasks=background,
        run_job=run_job,
        concept=manuscript.concept,
    )

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    usage = (
        db_session.query(ResearchUsage)
        .filter(ResearchUsage.manuscript_id == manuscript.id)
        .one()
    )
    assert usage.job_count == 1


def test_usage_row_initializes_job_count_from_existing_jobs(db_session):
    user, manuscript = _seed_user_and_manuscript(db_session)
    for _ in range(3):
        research_repo.create_research_job(
            db_session,
            user_id=user.id,
            manuscript_id=manuscript.id,
            message_id=uuid4(),
            claim_or_query="기존 job",
        )
    db_session.commit()

    usage = research_repo.get_or_create_research_usage(
        db_session,
        user_id=user.id,
        manuscript_id=manuscript.id,
    )
    db_session.commit()

    assert usage.job_count == 3
    assert usage.search_count == 0


def test_increment_search_count_on_usage_row(db_session):
    user, manuscript = _seed_user_and_manuscript(db_session)
    research_repo.increment_research_job_count(
        db_session,
        user_id=user.id,
        manuscript_id=manuscript.id,
    )
    usage = research_repo.increment_research_search_count(
        db_session,
        user_id=user.id,
        manuscript_id=manuscript.id,
    )
    db_session.commit()

    assert usage.job_count == 1
    assert usage.search_count == 1


def test_create_research_job_rejects_non_research_concepts(db_session):
    user, manuscript = _seed_user_and_manuscript(db_session)
    manuscript.concept = ConceptType.TIL
    db_session.commit()

    class _Background:
        def start(self, coroutine):
            coroutine.close()

    def run_job(_job_id):
        async def _run():
            return None

        return _run()

    with pytest.raises(ConflictError, match="딥다이브·수업 자료"):
        create_or_get_research_job(
            db_session,
            user_id=user.id,
            manuscript_id=manuscript.id,
            message_id=uuid4(),
            claim_or_query="일반론",
            background_tasks=_Background(),
            run_job=run_job,
            concept=manuscript.concept,
        )
