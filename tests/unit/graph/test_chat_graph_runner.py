import json
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.graph.chat_graph_runner import ChatGraphRunner
from app.models.manuscript import ConceptType, Manuscript, ManuscriptStatus
from app.models.research import ResponseComparisonRecord
from app.models.user import User
from tests.db_setup import prepare_test_database

pytestmark = pytest.mark.unit


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'runner.db'}")
    prepare_test_database(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_prepared_evidence(db_session):
    user = User(login_id=f"u-{uuid4().hex[:8]}", password_hash="x", nickname="n")
    db_session.add(user)
    db_session.flush()
    manuscript = Manuscript(
        user_id=user.id,
        topic="topic",
        concept=ConceptType.TECH_DEEPDIVE,
        status=ManuscriptStatus.DRAFTING,
    )
    db_session.add(manuscript)
    db_session.flush()
    record = ResponseComparisonRecord(
        research_job_id=uuid4(),
        user_id=user.id,
        manuscript_id=manuscript.id,
        message_id=uuid4(),
        baseline_body="baseline",
        grounded_body="grounded",
        prepared_evidence_json=json.dumps(
            {
                "items": [
                    {
                        "chunk_id": "chunk-a",
                        "source_id": "src-a",
                        "excerpt": "근거 본문",
                        "score": 0.9,
                        "title": "Title",
                        "url": "https://example.com/doc",
                    }
                ],
                "sufficiency": {
                    "sufficient": True,
                    "missing_aspects": [],
                    "supporting_chunk_ids": ["chunk-a"],
                    "reason_code": "matched_chunks",
                },
                "is_grounded": True,
                "warning_code": None,
            },
            ensure_ascii=False,
        ),
    )
    db_session.add(record)
    db_session.commit()
    return user, manuscript, record


@pytest.mark.asyncio
@pytest.mark.parametrize("user_action", ["say", "feedback"])
async def test_route_turn_consumes_prepared_evidence_for_chat_actions(
    db_session, user_action
):
    user, manuscript, record = _seed_prepared_evidence(db_session)

    class FakeGraph:
        async def ainvoke(self, *_args, **_kwargs):
            return {"user_action": user_action}

    runner = ChatGraphRunner(graph=FakeGraph(), storage=None, db_factory=None)
    state = await runner.route_turn(
        manuscript=manuscript,
        user=user,
        user_message="다음 질문",
        user_message_id=uuid4(),
        request_db_session=db_session,
        model="default",
    )

    db_session.refresh(record)
    assert state["user_action"] == user_action
    assert record.consumed_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("user_action", ["outline", "generate_document", "refuse"])
async def test_route_turn_keeps_prepared_evidence_for_non_chat_actions(
    db_session, user_action
):
    user, manuscript, record = _seed_prepared_evidence(db_session)

    class FakeGraph:
        async def ainvoke(self, *_args, **_kwargs):
            return {"user_action": user_action}

    runner = ChatGraphRunner(graph=FakeGraph(), storage=None, db_factory=None)
    state = await runner.route_turn(
        manuscript=manuscript,
        user=user,
        user_message="원고 작성해주세요",
        user_message_id=uuid4(),
        request_db_session=db_session,
        model="default",
    )

    db_session.refresh(record)
    assert record.consumed_at is None
