from app.models.manuscript import ConceptType
from app.models.user import User
from app.repositories import manuscript_repo


def _create_user(db_session, login_id):
    user = User(login_id=login_id, password_hash="x", nickname="n")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_create_persists_manuscript(db_session):
    # create()로 만든 원고는 소유자와 기본 상태(drafting)를 가진 채 DB에 저장되어야 한다.
    owner = _create_user(db_session, "repo_owner")
    manuscript = manuscript_repo.create(db_session, owner, "topic", ConceptType.ESSAY, None)

    assert manuscript.id is not None
    assert manuscript.user_id == owner.id
    assert manuscript.status.value == "drafting"


def test_list_by_user_only_returns_owned(db_session):
    # list_by_user()는 다른 사용자의 원고를 섞지 않고 본인 소유 원고만 반환해야 한다.
    owner = _create_user(db_session, "repo_list_a")
    other_user = _create_user(db_session, "repo_list_b")
    manuscript_repo.create(db_session, owner, "t1", ConceptType.ESSAY, None)
    manuscript_repo.create(db_session, other_user, "t2", ConceptType.ESSAY, None)

    owner_manuscripts = manuscript_repo.list_by_user(db_session, owner)

    assert len(owner_manuscripts) == 1
    assert owner_manuscripts[0].user_id == owner.id


def test_get_owned_returns_none_for_other_user(db_session):
    # get_owned()는 소유자가 아닌 사용자가 조회하면 None을 반환해 소유권 경계를 지켜야 한다.
    owner = _create_user(db_session, "repo_get_a")
    other_user = _create_user(db_session, "repo_get_b")
    manuscript = manuscript_repo.create(db_session, owner, "t", ConceptType.ESSAY, None)

    assert manuscript_repo.get_owned(db_session, other_user, manuscript.id) is None
    assert manuscript_repo.get_owned(db_session, owner, manuscript.id) is not None
