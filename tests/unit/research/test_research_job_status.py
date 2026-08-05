"""조사 job 상태 API 페이로드 검증."""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.manuscript import ConceptType, Manuscript, ManuscriptStatus
from app.models.research import (
    ResearchJob,
    ResearchJobStatus,
    ResearchSource,
    ResearchSourceScope,
    ResearchSourceStatus,
)
from app.models.user import User
from app.repositories import research_repo
from app.services.research_job_service import research_job_status_payload
from tests.db_setup import prepare_test_database

pytestmark = pytest.mark.unit


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'job_status.db'}")
    prepare_test_database(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_user_and_manuscript(db_session):
    user = User(login_id=f"u-{uuid4().hex[:8]}", password_hash="x", nickname="n")
    db_session.add(user)
    db_session.flush()
    manuscript = Manuscript(
        user_id=user.id,
        topic="status",
        concept=ConceptType.TECH_DEEPDIVE,
        status=ManuscriptStatus.DRAFTING,
    )
    db_session.add(manuscript)
    db_session.commit()
    return user, manuscript


def _make_source(
    *,
    user_id,
    manuscript_id,
    canonical_url: str,
    title: str,
) -> ResearchSource:
    scope = ResearchSourceScope.PUBLIC
    identity_key = research_repo.source_identity_key(
        scope, canonical_url, user_id, manuscript_id
    )
    source_id = research_repo.source_id_from_identity(identity_key)
    fetched_at = datetime(2026, 7, 1, 12, 0, 0)
    return ResearchSource(
        id=source_id,
        identity_key=identity_key,
        scope=scope,
        canonical_url=canonical_url,
        title=title,
        publisher="Example Pub",
        fetched_at=fetched_at,
        content_hash="abc123",
        storage_key=f"research_sources/{source_id}.json",
        language="ko",
        status=ResearchSourceStatus.INDEXED,
        embedding_model="test-model",
        embedding_dimension=8,
        chunk_schema_version="chunk-600-100-v1",
    )


def test_status_payload_includes_linked_sources(db_session):
    user, manuscript = _seed_user_and_manuscript(db_session)
    job = ResearchJob(
        user_id=user.id,
        manuscript_id=manuscript.id,
        status=ResearchJobStatus.RUNNING,
    )
    db_session.add(job)
    db_session.flush()

    first = _make_source(
        user_id=user.id,
        manuscript_id=manuscript.id,
        canonical_url="https://example.com/first",
        title="첫 번째 출처",
    )
    second = _make_source(
        user_id=user.id,
        manuscript_id=manuscript.id,
        canonical_url="https://example.com/second",
        title="두 번째 출처",
    )
    db_session.add_all([first, second])
    db_session.flush()
    research_repo.link_source_to_research_job(db_session, job, first)
    research_repo.link_source_to_research_job(db_session, job, second)
    db_session.commit()

    payload = research_job_status_payload(db_session, job)

    assert payload["id"] == str(job.id)
    assert payload["status"] == "running"
    assert payload["evidence_ready"] is False
    assert len(payload["sources"]) == 2
    by_url = {item["canonical_url"]: item for item in payload["sources"]}
    assert by_url["https://example.com/first"] == {
        "id": str(first.id),
        "title": "첫 번째 출처",
        "canonical_url": "https://example.com/first",
        "status": "indexed",
        "scope": "public",
        "publisher": "Example Pub",
        "fetched_at": "2026-07-01T12:00:00",
    }
    assert by_url["https://example.com/second"]["title"] == "두 번째 출처"


def test_status_payload_sources_empty_when_none_linked(db_session):
    user, manuscript = _seed_user_and_manuscript(db_session)
    job = ResearchJob(
        user_id=user.id,
        manuscript_id=manuscript.id,
        status=ResearchJobStatus.QUEUED,
    )
    db_session.add(job)
    db_session.commit()

    payload = research_job_status_payload(db_session, job)

    assert payload["sources"] == []
