from app.core.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


def apply_langfeather(graph):
    """compiled graph를 LangFeather로 감싼다. 비활성이면 원본을 그대로 반환한다."""
    if not settings.LANGFEATHER_ENABLED:
        return graph

    import langfeather

    langfeather.configure(endpoint=settings.LANGFEATHER_ENDPOINT)
    wrapped = langfeather.wrap_runnable(graph, name="think-chair")
    logger.info(
        "langfeather.enabled",
        endpoint=settings.LANGFEATHER_ENDPOINT,
    )
    return wrapped


def shutdown_langfeather() -> None:
    if not settings.LANGFEATHER_ENABLED:
        return

    import langfeather

    langfeather.shutdown()
