from functools import lru_cache

from app.services.storage.base import FileStorage
from app.services.storage.local import LocalFileStorage


@lru_cache
def get_file_storage() -> FileStorage:
    return LocalFileStorage()
