import hashlib

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import settings as default_settings
from app.llm.deepseek_call_log import DeepSeekGraphCallLogger
from app.logging import get_logger

logger = get_logger(__name__)

_registry: dict[str, BaseChatModel] = {}


def register(name: str, llm: BaseChatModel) -> None:
    _registry[name] = llm


def get(name: str = "default") -> BaseChatModel:
    return _registry[name]


def bootstrap(settings) -> None:
    register(
        "default",
        ChatOpenAI(
            openai_api_key=settings.DEEPSEEK_API_KEY,
            openai_api_base=settings.DEEPSEEK_API_BASE,
            model_name=settings.DEEPSEEK_MODEL,
            temperature=0.3,
            streaming=True,
            callbacks=[DeepSeekGraphCallLogger()],
        ),
    )
    logger.info("llm_registry.bootstrapped", model=settings.DEEPSEEK_MODEL)


def resolve_model_key(
    *,
    model: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> str:
    """턴별 모델 override를 registry key로 변환한다.

    세 값이 모두 비어있으면 override 없이 "default"를 그대로 쓴다.
    하나라도 있으면 나머지는 DeepSeek 설정값으로 채우고, 같은 조합은
    같은 key로 캐시해 ChatOpenAI 인스턴스를 재사용한다.
    """
    if not model and not api_base and not api_key:
        return "default"

    resolved_model = model or default_settings.DEEPSEEK_MODEL
    resolved_api_base = api_base or default_settings.DEEPSEEK_API_BASE
    resolved_api_key = api_key or default_settings.DEEPSEEK_API_KEY

    key = _override_key(resolved_model, resolved_api_base, resolved_api_key)
    if key not in _registry:
        register(
            key,
            ChatOpenAI(
                openai_api_key=resolved_api_key,
                openai_api_base=resolved_api_base,
                model_name=resolved_model,
                temperature=0.3,
                streaming=True,
                callbacks=[DeepSeekGraphCallLogger()],
            ),
        )
        logger.info(
            "llm_registry.override_registered",
            model=resolved_model,
            api_base=resolved_api_base,
        )
    return key


def _override_key(model: str, api_base: str, api_key: str) -> str:
    digest = hashlib.sha256(f"{api_base}|{model}|{api_key}".encode()).hexdigest()[:16]
    return f"override:{digest}"
