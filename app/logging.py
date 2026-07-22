import logging
from typing import Any


class EventLogger:
    """Structured event logger with a compact call-site API."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def debug(self, event: str, **fields: Any) -> None:
        self._log(logging.DEBUG, event, fields)

    def info(self, event: str, **fields: Any) -> None:
        self._log(logging.INFO, event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._log(logging.WARNING, event, fields)

    def error(self, event: str, *, exc_info: Any = None, **fields: Any) -> None:
        self._log(logging.ERROR, event, fields, exc_info=exc_info)

    def exception(self, event: str, **fields: Any) -> None:
        self._logger.exception("%s %s", event, fields)

    def _log(
        self, level: int, event: str, fields: dict[str, Any], exc_info: Any = None
    ) -> None:
        self._logger.log(level, "%s %s", event, fields, exc_info=exc_info)


def get_logger(name: str) -> EventLogger:
    return EventLogger(logging.getLogger(name))
