from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.manuscript import ConceptType, Manuscript, ManuscriptStatus
from app.models.research import ResearchJob, ResearchJobStatus
from app.models.user import User
from app.research.research_job_context import ResearchJobContext
from tests.db_setup import prepare_test_database

pytestmark = pytest.mark.unit


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ctx.db'}")
    prepare_test_database(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_job(db_session, status=ResearchJobStatus.QUEUED):
    user = User(login_id=f"u-{uuid4().hex[:8]}", password_hash="x", nickname="n")
    db_session.add(user)
    db_session.flush()
    manuscript = Manuscript(
        user_id=user.id,
        topic="t",
        concept=ConceptType.TECH_DEEPDIVE,
        status=ManuscriptStatus.DRAFTING,
    )
    db_session.add(manuscript)
    db_session.flush()
    job = ResearchJob(
        user_id=user.id,
        manuscript_id=manuscript.id,
        message_id=uuid4(),
        claim_or_query="claim",
        status=status,
    )
    db_session.add(job)
    db_session.commit()
    return job


def test_research_job_cancelled_and_mark_methods(db_session):
    running = _seed_job(db_session, status=ResearchJobStatus.RUNNING)
    assert running.cancelled() is False
    assert running.mark_cancelled() is True
    assert running.cancelled() is True
    assert running.mark_cancelled() is False

    failed = _seed_job(db_session, status=ResearchJobStatus.QUEUED)
    failed.mark_failed("boom")
    assert failed.status == ResearchJobStatus.FAILED
    assert failed.terminal_error == "boom"

    queued = _seed_job(db_session)
    queued.mark_running()
    assert queued.status == ResearchJobStatus.RUNNING
    queued.mark_outcome(ResearchJobStatus.PARTIAL)
    assert queued.status == ResearchJobStatus.PARTIAL


def test_begin_marks_running(db_session):
    job = _seed_job(db_session)
    ctx = ResearchJobContext(db_session, job.id)
    assert ctx.begin() is True
    assert ctx.job.status == ResearchJobStatus.RUNNING


def test_begin_rejects_cancelled(db_session):
    job = _seed_job(db_session, status=ResearchJobStatus.CANCELLED)
    ctx = ResearchJobContext(db_session, job.id)
    assert ctx.begin() is False


def test_reload_if_active_detects_external_cancel(db_session):
    job = _seed_job(db_session)
    ctx = ResearchJobContext(db_session, job.id)
    assert ctx.begin() is True

    other = db_session.get(ResearchJob, job.id)
    other.mark_cancelled()
    db_session.commit()

    assert ctx.reload_if_active() is False
