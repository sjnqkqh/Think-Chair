from pathlib import Path
from typing import Literal

import chromadb
from chromadb.errors import NotFoundError

EvidenceScope = Literal["public", "private"]

EVIDENCE_COLLECTION_NAMES: dict[EvidenceScope, str] = {
    "public": "research_public_v1",
    "private": "research_private_v1",
}


class EvidenceIndexContractMismatch(RuntimeError):
    pass


class ResearchEvidenceIndex:
    def __init__(
        self,
        path: Path,
        *,
        embedding_model: str,
        embedding_dimension: int,
        chunk_schema_version: str,
    ):
        self.client = chromadb.PersistentClient(path=path)
        self.index_contract = {
            "embedding_model": embedding_model,
            "embedding_dimension": embedding_dimension,
            "chunk_schema_version": chunk_schema_version,
        }
        self.collections = {
            scope: self._open_compatible_collection(name)
            for scope, name in EVIDENCE_COLLECTION_NAMES.items()
        }

    def _open_compatible_collection(self, name: str):
        try:
            collection = self.client.get_collection(name)
        except NotFoundError:
            return self.client.create_collection(name, metadata=self.index_contract)
        if collection.metadata != self.index_contract:
            raise EvidenceIndexContractMismatch(
                f"{name} uses a different embedding contract"
            )
        return collection

    def store_source_chunks(
        self,
        *,
        scope: EvidenceScope,
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

    def discard_chunks(self, scope: EvidenceScope, ids: list[str]) -> None:
        if ids:
            self.collections[scope].delete(ids=ids)

    def remove_source_evidence(
        self, scope: EvidenceScope, source_id: str
    ) -> None:
        self.collections[scope].delete(where={"source_id": source_id})

    def query_chunks(
        self,
        *,
        scope: EvidenceScope,
        query_embedding: list[float],
        limit: int,
        where: dict | None = None,
    ) -> list[dict]:
        collection = self.collections[scope]
        if collection.count() == 0:
            return []
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": min(limit, max(collection.count(), 1)),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        raw = collection.query(**kwargs)
        ids = (raw.get("ids") or [[]])[0]
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        results: list[dict] = []
        for index, chunk_id in enumerate(ids):
            results.append(
                {
                    "id": chunk_id,
                    "document": documents[index] if index < len(documents) else "",
                    "metadata": metadatas[index] if index < len(metadatas) else {},
                    "distance": distances[index] if index < len(distances) else None,
                }
            )
        return results
