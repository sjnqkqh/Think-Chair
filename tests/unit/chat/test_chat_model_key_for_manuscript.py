import pytest

from app.models.manuscript import ConceptType, Manuscript
from app.models.user import User
from app.llm import manuscript_settings
from app.services.chat_service import chat_model_key_for_manuscript
import app.services.chat_service as chat_service_module

pytestmark = pytest.mark.unit


def test_chat_model_key_for_manuscript_uses_stored_settings(db_session, monkeypatch):
    user = User(login_id="chat-llm-key", password_hash="x", nickname="n")
    db_session.add(user)
    db_session.commit()
    manuscript = Manuscript(user_id=user.id, topic="t", concept=ConceptType.TIL)
    db_session.add(manuscript)
    db_session.commit()
    manuscript_settings.save_llm_settings_for_manuscript(
        db_session,
        manuscript.id,
        provider="openai",
        model="gpt-5.6-terra",
        effort="medium",
    )
    captured = {}

    def fake_key(**kwargs):
        captured.update(kwargs)
        return "llm:openai:test"

    monkeypatch.setattr(
        chat_service_module.llm_registry, "chat_model_key_for", fake_key
    )

    key = chat_model_key_for_manuscript(db_session, manuscript.id)

    assert key == "llm:openai:test"
    assert captured == {
        "provider": "openai",
        "model": "gpt-5.6-terra",
        "effort": "medium",
    }


def test_chat_model_key_for_manuscript_clamps_stored_openai_max(
    db_session, monkeypatch
):
    user = User(login_id="chat-llm-clamp", password_hash="x", nickname="n")
    db_session.add(user)
    db_session.commit()
    manuscript = Manuscript(user_id=user.id, topic="t", concept=ConceptType.TIL)
    db_session.add(manuscript)
    db_session.commit()
    settings = manuscript_settings.llm_settings_for_manuscript(
        db_session, manuscript.id
    )
    settings.provider = "openai"
    settings.model = "gpt-5.6-luna"
    settings.effort = "max"
    db_session.commit()
    captured = {}

    def fake_key(**kwargs):
        captured.update(kwargs)
        return "llm:openai:clamped"

    monkeypatch.setattr(
        chat_service_module.llm_registry, "chat_model_key_for", fake_key
    )

    key = chat_model_key_for_manuscript(db_session, manuscript.id)

    assert key == "llm:openai:clamped"
    assert captured["effort"] == "xhigh"


def test_chat_model_key_for_manuscript_logs_choice_when_requested(
    db_session, monkeypatch, caplog
):
    user = User(login_id="chat-llm-log", password_hash="x", nickname="n")
    db_session.add(user)
    db_session.commit()
    manuscript = Manuscript(user_id=user.id, topic="t", concept=ConceptType.TIL)
    db_session.add(manuscript)
    db_session.commit()
    monkeypatch.setattr(
        chat_service_module.llm_registry,
        "chat_model_key_for",
        lambda **_kwargs: "default",
    )

    with caplog.at_level("INFO", logger="app.services.chat_service"):
        chat_model_key_for_manuscript(
            db_session, manuscript.id, log_choice=True
        )

    assert any(
        "chat.llm_selected" in record.message
        and "deepseek-v4-flash" in record.message
        for record in caplog.records
    )
