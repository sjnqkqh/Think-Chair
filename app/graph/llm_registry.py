from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

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
        ),
    )
    logger.info("llm_registry.bootstrapped", model=settings.DEEPSEEK_MODEL)
