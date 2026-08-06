import hashlib
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import settings as default_settings
from app.llm.deepseek_call_log import DeepSeekGraphCallLogger
from app.logging import get_logger

logger = get_logger(__name__)

_registry: dict[str, BaseChatModel] = {}

SUPPORTED_PROVIDERS = frozenset({"deepseek", "openai"})


def register(name: str, llm: BaseChatModel) -> None:
    _registry[name] = llm


def get(name: str = "default") -> BaseChatModel:
    return _registry[name]


def bootstrap(settings) -> None:
    register(
        "default",
        _build_chat_model(
            provider="deepseek",
            model=settings.DEEPSEEK_MODEL,
            effort="high",
            api_key=settings.DEEPSEEK_API_KEY,
            api_base=settings.DEEPSEEK_API_BASE,
        ),
    )
    logger.info("llm_registry.bootstrapped", model=settings.DEEPSEEK_MODEL)


def resolve_model_key(
    *,
    provider: str | None = None,
    model: str | None = None,
    effort: str | None = None,
) -> str:
    """요청의 provider/model/effort를 registry key로 변환한다.

    세 값이 모두 비어있으면 override 없이 "default"를 그대로 쓴다.
    하나라도 있으면 provider 기본값(deepseek)과 벤더별 기본 model/effort로
    채운 뒤, 같은 조합은 같은 key로 캐시한다.
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
    resolved_effort = effort or _default_effort(resolved_provider)
    api_key, api_base = _provider_credentials(resolved_provider)

    key = _selection_key(resolved_provider, resolved_model, resolved_effort)
    if key not in _registry:
        register(
            key,
            _build_chat_model(
                provider=resolved_provider,
                model=resolved_model,
                effort=resolved_effort,
                api_key=api_key,
                api_base=api_base,
            ),
        )
        logger.info(
            "llm_registry.selection_registered",
            provider=resolved_provider,
            model=resolved_model,
            effort=resolved_effort,
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


def _build_chat_model(
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
        "callbacks": [DeepSeekGraphCallLogger()],
        "reasoning_effort": effort,
    }
    if provider == "deepseek":
        if effort == "none":
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        else:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    return ChatOpenAI(**kwargs)


def _selection_key(provider: str, model: str, effort: str) -> str:
    digest = hashlib.sha256(f"{provider}|{model}|{effort}".encode()).hexdigest()[:16]
    return f"llm:{provider}:{digest}"
