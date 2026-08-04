from unittest.mock import MagicMock

import pytest

from app.graph.langfeather_tracing import apply_langfeather

pytestmark = pytest.mark.unit


def test_apply_langfeather_returns_original_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.graph.langfeather_tracing.settings.LANGFEATHER_ENABLED", True
    )
    graph = MagicMock(name="compiled-graph")

    assert apply_langfeather(graph) is graph


def test_apply_langfeather_wraps_compiled_graph_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "app.graph.langfeather_tracing.settings.LANGFEATHER_ENABLED", True
    )
    monkeypatch.setattr(
        "app.graph.langfeather_tracing.settings.LANGFEATHER_ENDPOINT",
        "http://127.0.0.1:4319",
    )
    graph = MagicMock(name="compiled-graph")
    wrapped = MagicMock(name="wrapped-graph")
    configure = MagicMock()
    wrap_runnable = MagicMock(return_value=wrapped)

    import langfeather

    monkeypatch.setattr(langfeather, "configure", configure)
    monkeypatch.setattr(langfeather, "wrap_runnable", wrap_runnable)

    result = apply_langfeather(graph)

    configure.assert_called_once_with(endpoint="http://127.0.0.1:4319")
    wrap_runnable.assert_called_once_with(graph, name="think-chair")
    assert result is wrapped
