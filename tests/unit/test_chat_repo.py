import pytest

from app.models.manuscript import ConceptType
from app.models.user import User
from app.repositories import chat_repo, manuscript_repo

pytestmark = pytest.mark.unit


def _manuscript(db_session, login_id):
    user = User(login_id=login_id, password_hash="x", nickname="n")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return manuscript_repo.create(db_session, user, "t", ConceptType.ESSAY, None)


def test_create_message_increments_sequence_per_manuscript(db_session):
    # 같은 원고에 저장된 메시지는 sequence가 1부터 순차 증가해야 한다.
    manuscript = _manuscript(db_session, "chatrepo_a")

    first = chat_repo.create_message(db_session, manuscript, "user", "안녕", None)
    second = chat_repo.create_message(
        db_session, manuscript, "assistant", "응답", "opening"
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert second.phase == "opening"


def test_create_message_sequence_isolated_between_manuscripts(db_session):
    # sequence는 원고별로 독립적이어야 한다(다른 원고 카운트에 영향 없음).
    manuscript_a = _manuscript(db_session, "chatrepo_b")
    manuscript_b = _manuscript(db_session, "chatrepo_c")

    chat_repo.create_message(db_session, manuscript_a, "user", "a1", None)
    chat_repo.create_message(db_session, manuscript_a, "user", "a2", None)
    first_b = chat_repo.create_message(db_session, manuscript_b, "user", "b1", None)

    assert first_b.sequence == 1
