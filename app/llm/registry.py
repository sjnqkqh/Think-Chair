import hashlib
from typing import Any
from urllib.parse import urljoin

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import settings as default_settings
from app.llm.call_log import ChatModelCallLogger
from app.llm.manuscript_settings import resolve_request_effort
from app.logging import get_logger

logger = get_logger(__name__)

_registry: dict[str, BaseChatModel] = {}

SUPPORTED_PROVIDERS = frozenset({"deepseek", "openai"})
_STARTUP_VERIFY_TIMEOUT_SECONDS = 20.0


def register(name: str, llm: BaseChatModel) -> None:
    _registry[name] = llm


def get(name: str = "default") -> BaseChatModel:
    return _registry[name]


def bootstrap(settings) -> None:
    register(
        "default",
        _openai_compatible_chat_model(
            provider="deepseek",
            model=settings.DEEPSEEK_MODEL,
            effort="high",
            api_key=settings.DEEPSEEK_API_KEY,
            api_base=settings.DEEPSEEK_API_BASE,
        ),
    )
    logger.info("llm_registry.bootstrapped", model=settings.DEEPSEEK_MODEL)


def verify_configured_providers(settings) -> None:
    """서버 기동 시 지원 provider 기본 모델이 실제로 호출 가능한지 검증한다.

    키가 없거나 probe 호출이 실패하면 RuntimeError로 기동을 중단한다.
    """
    providers = (
        (
            "deepseek",
            settings.DEEPSEEK_MODEL,
            settings.DEEPSEEK_API_KEY,
            settings.DEEPSEEK_API_BASE,
        ),
        (
            "openai",
            settings.OPENAI_MODEL,
            settings.OPENAI_API_KEY,
            settings.OPENAI_API_BASE,
        ),
    )
    for provider, _model, api_key, api_base in providers:
        if not (api_key or "").strip():
            raise RuntimeError(
                f"LLM provider {provider!r} API 키가 없다. "
                "서버 기동 전 환경변수를 설정해라."
            )
        if not (api_base or "").strip():
            raise RuntimeError(f"LLM provider {provider!r} API base가 없다.")

    with httpx.Client(timeout=_STARTUP_VERIFY_TIMEOUT_SECONDS) as client:
        for provider, model, api_key, api_base in providers:
            _probe_chat_completion(
                client,
                provider=provider,
                model=model,
                api_key=api_key.strip(),
                api_base=api_base.strip(),
            )
            logger.info(
                "llm_registry.startup_verified",
                provider=provider,
                model=model,
            )


def chat_model_key_for(
    *,
    provider: str | None = None,
    model: str | None = None,
    effort: str | None = None,
) -> str:
    """원고/턴이 쓸 채팅 모델 registry key를 돌려준다.

    세 값이 모두 비어있으면 기본 모델("default")을 쓴다.
    하나라도 있으면 provider 기본값(deepseek)과 벤더별 기본 model/effort로
    채운 뒤, 같은 조합은 같은 key로 재사용한다.
    """
    provider = (provider or "").strip().lower() or None
    model = (model or "").strip() or None
    effort = (effort or "").strip().lower() or None

    if not provider and not model and not effort:
        return "default"

    resolved_provider = provider or "deepseek"
    if resolved_provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"지원하지 않는 provider: {resolved_provider!r}. "
            f"사용 가능: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
        )

    resolved_model = model or _default_model(resolved_provider)
    resolved_effort = resolve_request_effort(
        provider=resolved_provider,
        effort=effort or _default_effort(resolved_provider),
    )
    api_key, api_base = _provider_credentials(resolved_provider)

    key = _chat_model_cache_key(resolved_provider, resolved_model, resolved_effort)
    if key not in _registry:
        register(
            key,
            _openai_compatible_chat_model(
                provider=resolved_provider,
                model=resolved_model,
                effort=resolved_effort,
                api_key=api_key,
                api_base=api_base,
            ),
        )
    return key


def _default_model(provider: str) -> str:
    if provider == "openai":
        return default_settings.OPENAI_MODEL
    return default_settings.DEEPSEEK_MODEL


def _default_effort(provider: str) -> str:
    if provider == "openai":
        return "medium"
    return "high"


def _provider_credentials(provider: str) -> tuple[str, str]:
    if provider == "openai":
        return default_settings.OPENAI_API_KEY, default_settings.OPENAI_API_BASE
    return default_settings.DEEPSEEK_API_KEY, default_settings.DEEPSEEK_API_BASE


def _openai_compatible_chat_model(
    *,
    provider: str,
    model: str,
    effort: str,
    api_key: str,
    api_base: str,
) -> ChatOpenAI:
    kwargs: dict[str, Any] = {
        "openai_api_key": api_key,
        "openai_api_base": api_base,
        "model_name": model,
        "temperature": 0.3,
        "streaming": True,
        "callbacks": [ChatModelCallLogger()],
        "reasoning_effort": effort,
    }
    if provider == "deepseek":
        if effort == "none":
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        else:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    return ChatOpenAI(**kwargs)


def _chat_model_cache_key(provider: str, model: str, effort: str) -> str:
    digest = hashlib.sha256(f"{provider}|{model}|{effort}".encode()).hexdigest()[:16]
    return f"llm:{provider}:{digest}"


def _probe_chat_completion(
    client: httpx.Client,
    *,
    provider: str,
    model: str,
    api_key: str,
    api_base: str,
) -> None:
    url = urljoin(api_base.rstrip("/") + "/", "chat/completions")
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
        "max_completion_tokens": 16,
    }
    if provider == "deepseek":
        # 기동 검증은 CoT 없이 최소 호출만 한다.
        body["thinking"] = {"type": "disabled"}
        body["reasoning_effort"] = "low"
        body["max_tokens"] = 16
        body.pop("max_completion_tokens", None)
    else:
        body["reasoning_effort"] = "low"

    try:
        response = client.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"LLM provider {provider!r} 기본 모델 {model!r} 호출 검증 실패: {exc}"
        ) from exc

    if response.status_code >= 400:
        detail = response.text[:300]
        raise RuntimeError(
            f"LLM provider {provider!r} 기본 모델 {model!r} 호출 검증 실패 "
            f"(HTTP {response.status_code}): {detail}"
        )
