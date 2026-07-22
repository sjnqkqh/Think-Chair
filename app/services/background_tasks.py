import asyncio
from collections.abc import Coroutine
from typing import Any

from app.logging import get_logger

logger = get_logger(__name__)


class BackgroundTaskRegistry:
    def __init__(self):
        self._tasks: set[asyncio.Task] = set()

    def start(self, coroutine: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            logger.error("background_task.failed", exc_info=exc)
