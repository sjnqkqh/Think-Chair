import json
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.manuscript import ConceptType, Manuscript, ManuscriptStatus
from app.models.research import ResearchJob, ResearchJobStatus, ResearchWebSearch
from app.models.user import User
from app.repositories import research_repo
from app.services.research_job_service import research_job_status_payload
from tests.db_setup import prepare_test_database

pytestmark = pytest.mark.unit


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'web_search_record.db'}")
    prepare_test_database(engine)
    return sessionmaker(bind=engine)()


def test_record_and_expose_brave_query_on_job_status(tmp_path):
    db = _session(tmp_path)
    user = User(login_id="brave-q", password_hash="x", nickname="b")
    db.add(user)
    db.flush()
    manuscript = Manuscript(
        user_id=user.id,
        topic="q",
        concept=ConceptType.TECH_DEEPDIVE,
        status=ManuscriptStatus.DRAFTING,
    )
    db.add(manuscript)
    db.flush()
    job = ResearchJob(
        id=uuid4(),
        user_id=user.id,
        manuscript_id=manuscript.id,
        claim_or_query="청크 크기는 보통 512다",
        status=ResearchJobStatus.RUNNING,
    )
    db.add(job)
    db.flush()

    research_repo.record_research_web_search(
        db,
        job,
        query="청크 크기는 보통 512다",
        max_results=3,
        hit_results=[
            {
                "url": "https://docs.example/chunk",
                "title": "Chunking",
                "provider_rank": 1,
            }
        ],
        error_code=None,
    )
    db.commit()

    payload = research_job_status_payload(db, job)
    assert payload["claim_or_query"] == "청크 크기는 보통 512다"
    assert len(payload["web_searches"]) == 1
    search = payload["web_searches"][0]
    assert search["query"] == "청크 크기는 보통 512다"
    assert search["provider"] == "brave"
    assert search["hits"][0]["url"] == "https://docs.example/chunk"

    stored = db.query(ResearchWebSearch).one()
    assert json.loads(stored.hit_results_json)[0]["title"] == "Chunking"
    db.close()
