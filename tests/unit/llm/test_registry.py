import pytest

from app.llm import registry as llm_registry

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_registry():
    """동적 등록 key가 다른 테스트로 새지 않게 원복한다."""
    before = set(llm_registry._registry)
    yield
    for key in set(llm_registry._registry) - before:
        del llm_registry._registry[key]


def test_chat_model_key_for_without_choice_returns_default():
    assert llm_registry.chat_model_key_for() == "default"
    assert (
        llm_registry.chat_model_key_for(provider=None, model=None, effort=None)
        == "default"
    )


def test_chat_model_key_for_rejects_unknown_provider():
    with pytest.raises(ValueError, match="provider"):
        llm_registry.chat_model_key_for(provider="anthropic")


def test_chat_model_key_for_deepseek_defaults(monkeypatch):
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_MODEL", "deepseek-v4-flash"
    )
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_API_BASE", "https://api.deepseek.com"
    )
    monkeypatch.setattr(llm_registry.default_settings, "DEEPSEEK_API_KEY", "ds-key")

    key = llm_registry.chat_model_key_for(provider="deepseek")
    llm = llm_registry.get(key)

    assert key != "default"
    assert llm.model_name == "deepseek-v4-flash"
    assert llm.openai_api_base == "https://api.deepseek.com"
    assert llm.reasoning_effort == "high"
    assert llm.extra_body == {"thinking": {"type": "enabled"}}


def test_chat_model_key_for_openai_defaults(monkeypatch):
    monkeypatch.setattr(llm_registry.default_settings, "OPENAI_MODEL", "gpt-5.6-luna")
    monkeypatch.setattr(
        llm_registry.default_settings, "OPENAI_API_BASE", "https://api.openai.com/v1"
    )
    monkeypatch.setattr(llm_registry.default_settings, "OPENAI_API_KEY", "sk-test")

    key = llm_registry.chat_model_key_for(provider="openai")
    llm = llm_registry.get(key)

    assert llm.model_name == "gpt-5.6-luna"
    assert llm.openai_api_base == "https://api.openai.com/v1"
    assert llm.reasoning_effort == "medium"
    assert llm.extra_body is None


def test_chat_model_key_for_custom_model_and_effort(monkeypatch):
    monkeypatch.setattr(llm_registry.default_settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        llm_registry.default_settings, "OPENAI_API_BASE", "https://api.openai.com/v1"
    )
    monkeypatch.setattr(llm_registry.default_settings, "OPENAI_MODEL", "gpt-5.6-luna")

    key = llm_registry.chat_model_key_for(
        provider="openai", model="gpt-5.6-sol", effort="high"
    )
    llm = llm_registry.get(key)

    assert llm.model_name == "gpt-5.6-sol"
    assert llm.reasoning_effort == "high"


def test_chat_model_key_for_reuses_same_choice(monkeypatch):
    monkeypatch.setattr(llm_registry.default_settings, "DEEPSEEK_API_KEY", "ds-key")
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_API_BASE", "https://api.deepseek.com"
    )
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_MODEL", "deepseek-v4-flash"
    )

    first = llm_registry.chat_model_key_for(
        provider="deepseek", model="deepseek-v4-pro", effort="max"
    )
    second = llm_registry.chat_model_key_for(
        provider="deepseek", model="deepseek-v4-pro", effort="max"
    )

    assert first == second


def test_chat_model_key_for_clamps_openai_max_to_xhigh(monkeypatch):
    monkeypatch.setattr(llm_registry.default_settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        llm_registry.default_settings, "OPENAI_API_BASE", "https://api.openai.com/v1"
    )
    monkeypatch.setattr(llm_registry.default_settings, "OPENAI_MODEL", "gpt-5.6-luna")

    key = llm_registry.chat_model_key_for(
        provider="openai", model="gpt-5.6-luna", effort="max"
    )
    llm = llm_registry.get(key)

    assert llm.reasoning_effort == "xhigh"


def test_chat_model_key_for_model_alone_uses_default_provider(monkeypatch):
    monkeypatch.setattr(llm_registry.default_settings, "DEEPSEEK_API_KEY", "ds-key")
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_API_BASE", "https://api.deepseek.com"
    )
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_MODEL", "deepseek-v4-flash"
    )

    key = llm_registry.chat_model_key_for(model="deepseek-v4-pro")
    llm = llm_registry.get(key)

    assert llm.model_name == "deepseek-v4-pro"
    assert llm.openai_api_base == "https://api.deepseek.com"
