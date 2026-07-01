import pytest

from app.core.exceptions import NotFoundError
from app.models.manuscript import ConceptType
from app.models.user import User
from app.schemas.manuscript import ManuscriptCreateRequest
from app.services import manuscript_service


def _create_user(db_session, login_id):
    user = User(login_id=login_id, password_hash="x", nickname="n")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_create_manuscript_delegates_to_repo(db_session):
    # create_manuscript()가 요청 payload를 그대로 repo.create()에 전달해 저장하는지 확인한다.
    owner = _create_user(db_session, "svc_owner")
    payload = ManuscriptCreateRequest(topic="t", concept=ConceptType.TIL)

    manuscript = manuscript_service.create_manuscript(db_session, owner, payload)

    assert manuscript.topic == "t"
    assert manuscript.concept == ConceptType.TIL


def test_get_manuscript_raises_404_when_not_owned(db_session):
    # 소유자가 아닌 사용자가 원고를 조회하면 NotFoundError(404)를 던져야 한다.
    owner = _create_user(db_session, "svc_owner2")
    stranger = _create_user(db_session, "svc_stranger")
    payload = ManuscriptCreateRequest(topic="t", concept=ConceptType.ESSAY)
    manuscript = manuscript_service.create_manuscript(db_session, owner, payload)

    with pytest.raises(NotFoundError) as exc_info:
        manuscript_service.get_manuscript(db_session, stranger, manuscript.id)

    assert exc_info.value.status_code == 404
