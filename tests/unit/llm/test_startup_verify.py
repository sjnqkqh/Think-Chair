from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from app.llm import registry as llm_registry

pytestmark = pytest.mark.unit


def _settings(**overrides):
    base = dict(
        DEEPSEEK_API_KEY="ds-key",
        DEEPSEEK_API_BASE="https://api.deepseek.com",
        DEEPSEEK_MODEL="deepseek-v4-flash",
        OPENAI_API_KEY="sk-test",
        OPENAI_API_BASE="https://api.openai.com/v1",
        OPENAI_MODEL="gpt-5.6-luna",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_verify_configured_providers_requires_api_keys():
    with pytest.raises(RuntimeError, match="openai"):
        llm_registry.verify_configured_providers(_settings(OPENAI_API_KEY=""))


def test_verify_configured_providers_probes_each_provider(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_post(url, *, headers=None, json=None, timeout=None):
        calls.append((url, json))
        return httpx.Response(200, json={"id": "ok", "choices": []})

    transport = MagicMock()
    client = MagicMock()
    client.post.side_effect = fake_post
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    monkeypatch.setattr(llm_registry.httpx, "Client", lambda **_: client)

    llm_registry.verify_configured_providers(_settings())

    assert len(calls) == 2
    urls = {url for url, _ in calls}
    assert "https://api.deepseek.com/chat/completions" in urls
    assert "https://api.openai.com/v1/chat/completions" in urls

    deepseek_body = next(
        body for url, body in calls if url.endswith("api.deepseek.com/chat/completions")
    )
    assert deepseek_body["model"] == "deepseek-v4-flash"
    assert deepseek_body["thinking"] == {"type": "disabled"}

    openai_body = next(
        body for url, body in calls if "api.openai.com" in url
    )
    assert openai_body["model"] == "gpt-5.6-luna"
    assert openai_body["reasoning_effort"] == "low"


def test_verify_configured_providers_fails_on_http_error(monkeypatch):
    client = MagicMock()
    client.post.return_value = httpx.Response(
        401, json={"error": {"message": "invalid api key"}}
    )
    client.__enter__.return_value = client
    client.__exit__.return_value = None
    monkeypatch.setattr(llm_registry.httpx, "Client", lambda **_: client)

    with pytest.raises(RuntimeError, match="deepseek"):
        llm_registry.verify_configured_providers(_settings())
