from abc import ABC, abstractmethod


class FileStorage(ABC):
    @abstractmethod
    def save(self, key: str, content: bytes) -> str: ...

    @abstractmethod
    def read(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...
