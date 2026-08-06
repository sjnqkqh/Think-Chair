import pytest

from app.graph import llm_registry

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_registry():
    """동적 등록 key가 다른 테스트로 새지 않게 원복한다."""
    before = set(llm_registry._registry)
    yield
    for key in set(llm_registry._registry) - before:
        del llm_registry._registry[key]


def test_resolve_model_key_without_selection_returns_default():
    assert llm_registry.resolve_model_key() == "default"
    assert (
        llm_registry.resolve_model_key(provider=None, model=None, effort=None)
        == "default"
    )


def test_resolve_model_key_rejects_unknown_provider():
    with pytest.raises(ValueError, match="provider"):
        llm_registry.resolve_model_key(provider="anthropic")


def test_resolve_model_key_deepseek_defaults(monkeypatch):
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_MODEL", "deepseek-v4-flash"
    )
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_API_BASE", "https://api.deepseek.com"
    )
    monkeypatch.setattr(llm_registry.default_settings, "DEEPSEEK_API_KEY", "ds-key")

    key = llm_registry.resolve_model_key(provider="deepseek")
    llm = llm_registry.get(key)

    assert key != "default"
    assert llm.model_name == "deepseek-v4-flash"
    assert llm.openai_api_base == "https://api.deepseek.com"
    assert llm.reasoning_effort == "high"
    assert llm.extra_body == {"thinking": {"type": "enabled"}}


def test_resolve_model_key_openai_defaults(monkeypatch):
    monkeypatch.setattr(llm_registry.default_settings, "OPENAI_MODEL", "gpt-5.6-luna")
    monkeypatch.setattr(
        llm_registry.default_settings, "OPENAI_API_BASE", "https://api.openai.com/v1"
    )
    monkeypatch.setattr(llm_registry.default_settings, "OPENAI_API_KEY", "sk-test")

    key = llm_registry.resolve_model_key(provider="openai")
    llm = llm_registry.get(key)

    assert llm.model_name == "gpt-5.6-luna"
    assert llm.openai_api_base == "https://api.openai.com/v1"
    assert llm.reasoning_effort == "medium"
    assert llm.extra_body is None


def test_resolve_model_key_custom_model_and_effort(monkeypatch):
    monkeypatch.setattr(llm_registry.default_settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        llm_registry.default_settings, "OPENAI_API_BASE", "https://api.openai.com/v1"
    )
    monkeypatch.setattr(llm_registry.default_settings, "OPENAI_MODEL", "gpt-5.6-luna")

    key = llm_registry.resolve_model_key(
        provider="openai", model="gpt-5.6-sol", effort="high"
    )
    llm = llm_registry.get(key)

    assert llm.model_name == "gpt-5.6-sol"
    assert llm.reasoning_effort == "high"


def test_resolve_model_key_caches_same_selection(monkeypatch):
    monkeypatch.setattr(llm_registry.default_settings, "DEEPSEEK_API_KEY", "ds-key")
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_API_BASE", "https://api.deepseek.com"
    )
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_MODEL", "deepseek-v4-flash"
    )

    first = llm_registry.resolve_model_key(
        provider="deepseek", model="deepseek-v4-pro", effort="max"
    )
    second = llm_registry.resolve_model_key(
        provider="deepseek", model="deepseek-v4-pro", effort="max"
    )

    assert first == second


def test_resolve_model_key_model_alone_uses_default_provider(monkeypatch):
    monkeypatch.setattr(llm_registry.default_settings, "DEEPSEEK_API_KEY", "ds-key")
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_API_BASE", "https://api.deepseek.com"
    )
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_MODEL", "deepseek-v4-flash"
    )

    key = llm_registry.resolve_model_key(model="deepseek-v4-pro")
    llm = llm_registry.get(key)

    assert llm.model_name == "deepseek-v4-pro"
    assert llm.openai_api_base == "https://api.deepseek.com"
