import random
import time
from typing import Callable, TypeVar, Any

from app.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def execute_with_retry(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 5,
    base_delay: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    **kwargs: Any,
) -> T:
    """임의의 함수를 실행하면서 지정된 예외에 대해 지수 백오프 재시도를 제공하는 헬퍼 함수."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            if attempt == max_retries - 1:
                logger.error(
                    "retry.exhausted",
                    function=getattr(func, "__name__", str(func)),
                    max_retries=max_retries,
                    error=str(e),
                )
                raise e

            # 지수 백오프 계산: base_delay * (2 ** attempt) + jitter
            delay = base_delay * (2**attempt) + random.uniform(0, 0.1)
            logger.warning(
                "retry.scheduled",
                function=getattr(func, "__name__", str(func)),
                error=str(e),
                delay_seconds=delay,
                attempt=attempt + 1,
                max_retries=max_retries,
            )
            time.sleep(delay)
    raise RuntimeError("Unexpected end of retry loop")
