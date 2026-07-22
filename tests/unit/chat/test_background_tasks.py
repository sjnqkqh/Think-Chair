import asyncio
import logging

import pytest

from app.services.background_tasks import BackgroundTaskRegistry

pytestmark = pytest.mark.unit


async def _wait_until(predicate, timeout: float = 1.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.01)
    return True


async def test_failing_task_is_logged_and_swallowed(caplog):
    registry = BackgroundTaskRegistry()

    async def boom():
        raise ValueError("실패")

    with caplog.at_level(logging.ERROR, logger="app.services.background_tasks"):
        registry.start(boom())
        logged = await _wait_until(
            lambda: any("background_task.failed" in r.message for r in caplog.records)
        )

    assert logged


async def test_completed_task_runs_then_reference_is_discarded():
    registry = BackgroundTaskRegistry()
    ran = asyncio.Event()

    async def job():
        ran.set()

    registry.start(job())

    assert await _wait_until(lambda: ran.is_set() and not registry._tasks)
