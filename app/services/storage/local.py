import logging
from pathlib import Path

from app.core.config import settings
from app.services.storage.base import FileStorage

logger = logging.getLogger(__name__)


class LocalFileStorage(FileStorage):
    def __init__(self, root: Path | None = None):
        self.root = root if root is not None else settings.STORAGE_ROOT

    def save(self, key: str, content: bytes) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        logger.info("file saved: key=%s bytes=%d", key, len(content))
        return key

    def read(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def delete(self, key: str) -> None:
        (self.root / key).unlink(missing_ok=True)
        logger.info("file deleted: key=%s", key)
