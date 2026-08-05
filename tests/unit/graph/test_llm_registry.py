import pytest

from app.graph import llm_registry

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_registry():
    """override로 등록된 key가 다른 테스트로 새지 않게 원복한다."""
    before = set(llm_registry._registry)
    yield
    for key in set(llm_registry._registry) - before:
        del llm_registry._registry[key]


def test_resolve_model_key_without_override_returns_default():
    assert llm_registry.resolve_model_key() == "default"
    assert (
        llm_registry.resolve_model_key(model=None, api_base=None, api_key=None)
        == "default"
    )


def test_resolve_model_key_registers_custom_model_and_base():
    key = llm_registry.resolve_model_key(
        model="gpt-4o-mini",
        api_base="https://api.openai.com/v1",
        api_key="sk-test",
    )

    assert key != "default"
    registered = llm_registry.get(key)
    assert registered.model_name == "gpt-4o-mini"
    assert registered.openai_api_base == "https://api.openai.com/v1"


def test_resolve_model_key_fills_missing_fields_from_deepseek_settings(monkeypatch):
    monkeypatch.setattr(llm_registry.default_settings, "DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setattr(
        llm_registry.default_settings, "DEEPSEEK_API_BASE", "https://api.deepseek.com"
    )
    monkeypatch.setattr(llm_registry.default_settings, "DEEPSEEK_API_KEY", "ds-key")

    key = llm_registry.resolve_model_key(api_base="https://proxy.example.com")

    registered = llm_registry.get(key)
    assert registered.model_name == "deepseek-chat"
    assert registered.openai_api_base == "https://proxy.example.com"


def test_resolve_model_key_caches_same_override():
    first = llm_registry.resolve_model_key(model="gpt-4o-mini", api_base="https://x")
    second = llm_registry.resolve_model_key(model="gpt-4o-mini", api_base="https://x")

    assert first == second
