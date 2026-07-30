from pathlib import Path
from typing import Literal

import chromadb
from chromadb.errors import NotFoundError

Scope = Literal["public", "private"]

COLLECTION_NAMES: dict[Scope, str] = {
    "public": "research_public_v1",
    "private": "research_private_v1",
}


class EmbeddingConfigurationMismatch(RuntimeError):
    pass


class ResearchVectorStore:
    def __init__(
        self,
        path: Path,
        *,
        embedding_model: str,
        embedding_dimension: int,
        chunk_schema_version: str,
    ):
        self.client = chromadb.PersistentClient(path=path)
        self.contract = {
            "embedding_model": embedding_model,
            "embedding_dimension": embedding_dimension,
            "chunk_schema_version": chunk_schema_version,
        }
        self.collections = {
            scope: self._open_collection(name)
            for scope, name in COLLECTION_NAMES.items()
        }

    def _open_collection(self, name: str):
        try:
            collection = self.client.get_collection(name)
        except NotFoundError:
            return self.client.create_collection(name, metadata=self.contract)
        if collection.metadata != self.contract:
            raise EmbeddingConfigurationMismatch(
                f"{name} uses a different embedding contract"
            )
        return collection

    def upsert(
        self,
        *,
        scope: Scope,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None:
        self.collections[scope].upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def delete(self, scope: Scope, ids: list[str]) -> None:
        if ids:
            self.collections[scope].delete(ids=ids)

    def delete_source(self, scope: Scope, source_id: str) -> None:
        self.collections[scope].delete(where={"source_id": source_id})

    def count(self, scope: Scope) -> int:
        return self.collections[scope].count()

    def get(self, scope: Scope, ids: list[str] | None = None):
        return self.collections[scope].get(
            ids=ids,
            include=["documents", "metadatas"],
        )
