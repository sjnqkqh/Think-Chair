import datetime
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import NotFoundError
from app.models.manuscript import ConceptType, ManuscriptVersion
from app.models.user import User
from app.schemas.manuscript import ManuscriptCreateRequest
from app.services import manuscript_service

pytestmark = pytest.mark.unit


def _create_user(db_session, login_id):
    user = User(login_id=login_id, password_hash="x", nickname="n")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_create_manuscript_delegates_payload_to_repo(monkeypatch, db_session):
    # 서비스는 요청 payload의 각 필드를 풀어 repo.create()에 그대로 위임해야 한다.
    owner = _create_user(db_session, "svc_owner")
    payload = ManuscriptCreateRequest(topic="t", concept=ConceptType.TIL)
    spy = (
        MagicMock()
    )  # 서비스가 반환 객체의 .id/.concept를 로깅하므로 목 객체를 돌려준다
    monkeypatch.setattr(manuscript_service.manuscript_repo, "create", spy)

    result = manuscript_service.create_manuscript(db_session, owner, payload)

    assert result is spy.return_value
    spy.assert_called_once_with(
        db_session, owner, payload.topic, payload.concept, payload.audience_level
    )


def test_get_manuscript_raises_404_when_not_owned(db_session):
    # 소유자가 아닌 사용자가 원고를 조회하면 NotFoundError(404)를 던져야 한다.
    owner = _create_user(db_session, "svc_owner2")
    stranger = _create_user(db_session, "svc_stranger")
    payload = ManuscriptCreateRequest(topic="t", concept=ConceptType.ESSAY)
    manuscript = manuscript_service.create_manuscript(db_session, owner, payload)

    with pytest.raises(NotFoundError) as exc_info:
        manuscript_service.get_manuscript(db_session, stranger, manuscript.id)

    assert exc_info.value.status_code == 404


def test_get_manuscript_not_found_is_logged(db_session, caplog):
    # 원고를 찾지 못했을 때 manuscript_id/user_id가 포함된 warning 로그를 남겨야 한다.
    owner = _create_user(db_session, "svc_owner3")
    stranger = _create_user(db_session, "svc_stranger2")
    payload = ManuscriptCreateRequest(topic="t", concept=ConceptType.ESSAY)
    manuscript = manuscript_service.create_manuscript(db_session, owner, payload)

    with caplog.at_level("WARNING", logger="app.services.manuscript_service"):
        with pytest.raises(NotFoundError):
            manuscript_service.get_manuscript(db_session, stranger, manuscript.id)

    assert any(
        "manuscript.not_found_or_not_owned" in record.message
        for record in caplog.records
    )


def test_get_version_file_uses_kind_specific_filename(db_session):
    owner = _create_user(db_session, "svc_version_owner")
    manuscript = manuscript_service.create_manuscript(
        db_session,
        owner,
        ManuscriptCreateRequest(topic="버전 표시 테스트", concept=ConceptType.TIL),
    )
    outline = ManuscriptVersion(
        manuscript_id=manuscript.id,
        kind="outline",
        revision=1,
        storage_key="outlines/test.md",
        created_at=datetime.datetime(2026, 7, 8, 0, 6),
    )
    document = ManuscriptVersion(
        manuscript_id=manuscript.id,
        kind="document",
        revision=1,
        storage_key="documents/test.md",
        created_at=datetime.datetime(2026, 7, 8, 0, 7),
    )
    db_session.add_all([outline, document])
    db_session.commit()
    storage = MagicMock()
    storage.read.return_value = b"content"

    outline_filename, _ = manuscript_service.get_version_file(
        db_session, owner, manuscript.id, outline.id, storage
    )
    document_filename, _ = manuscript_service.get_version_file(
        db_session, owner, manuscript.id, document.id, storage
    )

    assert outline_filename == "버전_표시_테스트_개요_01.md"
    assert document_filename == "버전_표시_테스트_문서_01.md"
