import time
import random
import logging
from typing import Callable, TypeVar, Any

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    max_retries: int = 5,
    base_delay: float = 0.5,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """동기 함수 호출 시 지정된 예외에 대해 지수 백오프 재시도를 적용하는 데코레이터.
    
    기본 지연 시간(0.5초)으로 시작해 시도할 때마다 대기 시간을 2배씩 늘리며 미세한 jitter를 섞습니다.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries - 1:
                        logger.error(
                            f"Failed to execute {func.__name__} after {max_retries} attempts due to: {e}"
                        )
                        raise e
                    
                    # 지수 백오프 계산: base_delay * (2 ** attempt) + jitter
                    delay = base_delay * (2**attempt) + random.uniform(0, 0.1)
                    logger.warning(
                        f"Error in {func.__name__} ({e}). Retrying in {delay:.2f} seconds... (Attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
            raise RuntimeError("Unexpected end of retry loop")
        return wrapper
    return decorator


def execute_with_retry(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 5,
    base_delay: float = 0.5,
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
                    f"Failed to execute {func.__name__ if hasattr(func, '__name__') else str(func)} "
                    f"after {max_retries} attempts due to: {e}"
                )
                raise e
            
            # 지수 백오프 계산: base_delay * (2 ** attempt) + jitter
            delay = base_delay * (2**attempt) + random.uniform(0, 0.1)
            logger.warning(
                f"Error executing {func.__name__ if hasattr(func, '__name__') else str(func)} ({e}). "
                f"Retrying in {delay:.2f} seconds... (Attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(delay)
    raise RuntimeError("Unexpected end of retry loop")
