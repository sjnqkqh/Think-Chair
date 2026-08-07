import pytest

from app.models.manuscript import ConceptType, Manuscript
from app.models.user import User
from app.llm import manuscript_settings as settings_service

pytestmark = pytest.mark.unit


def _create_user(db_session, login_id: str) -> User:
    user = User(login_id=login_id, password_hash="x", nickname="n")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_manuscript(db_session, user: User) -> Manuscript:
    manuscript = Manuscript(
        user_id=user.id,
        topic="설정 테스트",
        concept=ConceptType.TIL,
    )
    db_session.add(manuscript)
    db_session.commit()
    db_session.refresh(manuscript)
    return manuscript


def test_llm_settings_for_manuscript_returns_deepseek_defaults(db_session):
    user = _create_user(db_session, "llm_settings_defaults")
    manuscript = _create_manuscript(db_session, user)

    settings = settings_service.llm_settings_for_manuscript(db_session, manuscript.id)

    assert settings.manuscript_id == manuscript.id
    assert settings.provider == "deepseek"
    assert settings.model == "deepseek-v4-flash"
    assert settings.effort == "high"


def test_llm_settings_for_manuscript_reuses_existing_row(db_session):
    user = _create_user(db_session, "llm_settings_reuse")
    manuscript = _create_manuscript(db_session, user)
    first = settings_service.llm_settings_for_manuscript(db_session, manuscript.id)
    first.provider = "openai"
    first.model = "gpt-5.6-luna"
    first.effort = "medium"
    db_session.commit()

    second = settings_service.llm_settings_for_manuscript(db_session, manuscript.id)

    assert second.provider == "openai"
    assert second.model == "gpt-5.6-luna"
    assert second.effort == "medium"


def test_save_llm_settings_for_manuscript_persists_valid_choice(db_session):
    user = _create_user(db_session, "llm_settings_update")
    manuscript = _create_manuscript(db_session, user)

    settings = settings_service.save_llm_settings_for_manuscript(
        db_session,
        manuscript.id,
        provider="openai",
        model="gpt-5.6-sol",
        effort="low",
    )

    assert settings.provider == "openai"
    assert settings.model == "gpt-5.6-sol"
    assert settings.effort == "low"
    reloaded = settings_service.llm_settings_for_manuscript(db_session, manuscript.id)
    assert reloaded.model == "gpt-5.6-sol"


def test_save_llm_settings_for_manuscript_rejects_unknown_provider(db_session):
    user = _create_user(db_session, "llm_settings_bad_provider")
    manuscript = _create_manuscript(db_session, user)

    with pytest.raises(ValueError, match="provider"):
        settings_service.save_llm_settings_for_manuscript(
            db_session,
            manuscript.id,
            provider="anthropic",
            model="deepseek-v4-flash",
            effort="high",
        )


def test_save_llm_settings_coerces_model_when_not_allowed_for_provider(db_session):
    """provider 허용 목록 밖 model이면 해당 provider 기본 모델로 교정한다."""
    user = _create_user(db_session, "llm_settings_coerce")
    manuscript = _create_manuscript(db_session, user)

    settings = settings_service.save_llm_settings_for_manuscript(
        db_session,
        manuscript.id,
        provider="openai",
        model="deepseek-v4-pro",
        effort="medium",
    )

    assert settings.provider == "openai"
    assert settings.model == "gpt-5.6-luna"
    assert settings.effort == "medium"


def test_save_llm_settings_for_manuscript_rejects_unknown_effort(db_session):
    user = _create_user(db_session, "llm_settings_bad_effort")
    manuscript = _create_manuscript(db_session, user)

    with pytest.raises(ValueError, match="effort"):
        settings_service.save_llm_settings_for_manuscript(
            db_session,
            manuscript.id,
            provider="deepseek",
            model="deepseek-v4-flash",
            effort="ultra",
        )


def test_save_llm_settings_rejects_openai_max_effort(db_session):
    """OpenAI Chat Completions는 max를 거부한다. Luna 등 gpt-5.6-* 공통."""
    user = _create_user(db_session, "llm_settings_openai_max")
    manuscript = _create_manuscript(db_session, user)

    with pytest.raises(ValueError, match="effort"):
        settings_service.save_llm_settings_for_manuscript(
            db_session,
            manuscript.id,
            provider="openai",
            model="gpt-5.6-luna",
            effort="max",
        )


def test_save_llm_settings_allows_deepseek_max_effort(db_session):
    user = _create_user(db_session, "llm_settings_deepseek_max")
    manuscript = _create_manuscript(db_session, user)

    settings = settings_service.save_llm_settings_for_manuscript(
        db_session,
        manuscript.id,
        provider="deepseek",
        model="deepseek-v4-pro",
        effort="max",
    )

    assert settings.effort == "max"


def test_resolve_request_effort_clamps_openai_max_to_xhigh():
    assert (
        settings_service.resolve_request_effort(provider="openai", effort="max")
        == "xhigh"
    )
    assert (
        settings_service.resolve_request_effort(provider="openai", effort="high")
        == "high"
    )
    assert (
        settings_service.resolve_request_effort(provider="deepseek", effort="max")
        == "max"
    )
