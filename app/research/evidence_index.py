"""조사 근거 벡터 인덱스 (Postgres pgvector / 테스트용 SQLite)."""

from __future__ import annotations

import math
from typing import Any, Literal

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, String, Text, Column, MetaData, Table, create_engine, select, delete, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

EvidenceScope = Literal["public", "private"]

EVIDENCE_COLLECTION_NAMES: dict[EvidenceScope, str] = {
    "public": "research_public_v1",
    "private": "research_private_v1",
}

_CONTRACT_TABLE = "evidence_index_contracts"


class EvidenceIndexContractMismatch(RuntimeError):
    pass


def _is_sqlite(database_url: str) -> bool:
    return database_url.startswith("sqlite:")


def _l2_distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _metadata_matches(metadata: dict, where: dict | None) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_metadata_matches(metadata, clause) for clause in where["$and"])
    if "$or" in where:
        return any(_metadata_matches(metadata, clause) for clause in where["$or"])
    for key, expected in where.items():
        if metadata.get(key) != expected:
            return False
    return True


class ResearchEvidenceIndex:
    def __init__(
        self,
        database_url: str,
        *,
        embedding_model: str,
        embedding_dimension: int,
        chunk_schema_version: str,
    ):
        self.database_url = database_url
        self.embedding_dimension = embedding_dimension
        self.index_contract = {
            "embedding_model": embedding_model,
            "embedding_dimension": embedding_dimension,
            "chunk_schema_version": chunk_schema_version,
        }
        self._sqlite = _is_sqlite(database_url)
        self.engine: Engine = create_engine(database_url)
        self._session_factory = sessionmaker(
            bind=self.engine, autocommit=False, autoflush=False
        )
        self._metadata = MetaData()
        self._chunk_tables: dict[str, Table] = {}
        self._ensure_extension()
        self._ensure_contract_table()
        for scope, name in EVIDENCE_COLLECTION_NAMES.items():
            self._open_compatible_collection(name)

    def _ensure_extension(self) -> None:
        if self._sqlite:
            return
        with self.engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    def _ensure_contract_table(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_CONTRACT_TABLE} (
                        collection_name VARCHAR(128) PRIMARY KEY,
                        embedding_model VARCHAR(255) NOT NULL,
                        embedding_dimension INTEGER NOT NULL,
                        chunk_schema_version VARCHAR(128) NOT NULL
                    )
                    """
                )
            )

    def _chunk_table(self, collection_name: str) -> Table:
        if collection_name in self._chunk_tables:
            return self._chunk_tables[collection_name]
        table_name = f"evidence_chunks__{collection_name}"
        embedding_type = (
            JSON() if self._sqlite else Vector(self.embedding_dimension)
        )
        table = Table(
            table_name,
            self._metadata,
            Column("id", String(255), primary_key=True),
            Column("document", Text, nullable=False),
            Column("embedding", embedding_type, nullable=False),
            Column("metadata_json", JSON, nullable=False),
            extend_existing=True,
        )
        table.create(self.engine, checkfirst=True)
        self._chunk_tables[collection_name] = table
        return table

    def _open_compatible_collection(self, name: str) -> None:
        with self._session_factory() as session:
            row = session.execute(
                text(
                    f"SELECT embedding_model, embedding_dimension, chunk_schema_version "
                    f"FROM {_CONTRACT_TABLE} WHERE collection_name = :name"
                ),
                {"name": name},
            ).mappings().first()
            if row is None:
                session.execute(
                    text(
                        f"""
                        INSERT INTO {_CONTRACT_TABLE}
                        (collection_name, embedding_model, embedding_dimension, chunk_schema_version)
                        VALUES (:name, :model, :dim, :schema)
                        """
                    ),
                    {
                        "name": name,
                        "model": self.index_contract["embedding_model"],
                        "dim": self.index_contract["embedding_dimension"],
                        "schema": self.index_contract["chunk_schema_version"],
                    },
                )
                session.commit()
            else:
                existing = {
                    "embedding_model": row["embedding_model"],
                    "embedding_dimension": int(row["embedding_dimension"]),
                    "chunk_schema_version": row["chunk_schema_version"],
                }
                if existing != self.index_contract:
                    raise EvidenceIndexContractMismatch(
                        f"{name} uses a different embedding contract"
                    )
        self._chunk_table(name)

    def _collection_name(self, scope: EvidenceScope) -> str:
        return EVIDENCE_COLLECTION_NAMES[scope]

    def store_source_chunks(
        self,
        *,
        scope: EvidenceScope,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
    ) -> None:
        table = self._chunk_table(self._collection_name(scope))
        with self._session_factory() as session:
            for chunk_id, document, embedding, metadata in zip(
                ids, documents, embeddings, metadatas, strict=True
            ):
                session.execute(delete(table).where(table.c.id == chunk_id))
                session.execute(
                    table.insert().values(
                        id=chunk_id,
                        document=document,
                        embedding=embedding,
                        metadata_json=metadata,
                    )
                )
            session.commit()

    def discard_chunks(self, scope: EvidenceScope, ids: list[str]) -> None:
        if not ids:
            return
        table = self._chunk_table(self._collection_name(scope))
        with self._session_factory() as session:
            session.execute(delete(table).where(table.c.id.in_(ids)))
            session.commit()

    def remove_source_evidence(self, scope: EvidenceScope, source_id: str) -> None:
        table = self._chunk_table(self._collection_name(scope))
        with self._session_factory() as session:
            rows = session.execute(select(table.c.id, table.c.metadata_json)).all()
            to_delete = [
                row.id
                for row in rows
                if (row.metadata_json or {}).get("source_id") == source_id
            ]
            if to_delete:
                session.execute(delete(table).where(table.c.id.in_(to_delete)))
                session.commit()

    def count_chunks(self, scope: EvidenceScope) -> int:
        table = self._chunk_table(self._collection_name(scope))
        with self._session_factory() as session:
            return len(session.execute(select(table.c.id)).all())

    def list_metadatas(self, scope: EvidenceScope) -> list[dict]:
        table = self._chunk_table(self._collection_name(scope))
        with self._session_factory() as session:
            rows = session.execute(select(table.c.metadata_json)).all()
            return [dict(row.metadata_json or {}) for row in rows]

    def query_chunks(
        self,
        *,
        scope: EvidenceScope,
        query_embedding: list[float],
        limit: int,
        where: dict | None = None,
    ) -> list[dict]:
        if limit <= 0:
            return []
        table = self._chunk_table(self._collection_name(scope))
        with self._session_factory() as session:
            if self.count_chunks(scope) == 0:
                return []
            if self._sqlite:
                return self._query_sqlite(
                    session, table, query_embedding, limit, where
                )
            return self._query_pgvector(
                session, table, query_embedding, limit, where
            )

    def _query_sqlite(
        self,
        session: Session,
        table: Table,
        query_embedding: list[float],
        limit: int,
        where: dict | None,
    ) -> list[dict]:
        rows = session.execute(
            select(table.c.id, table.c.document, table.c.embedding, table.c.metadata_json)
        ).all()
        scored: list[tuple[float, Any]] = []
        for row in rows:
            metadata = dict(row.metadata_json or {})
            if not _metadata_matches(metadata, where):
                continue
            embedding = list(row.embedding)
            scored.append((_l2_distance(query_embedding, embedding), row))
        scored.sort(key=lambda item: item[0])
        results: list[dict] = []
        for distance, row in scored[:limit]:
            results.append(
                {
                    "id": row.id,
                    "document": row.document,
                    "metadata": dict(row.metadata_json or {}),
                    "distance": distance,
                }
            )
        return results

    def _query_pgvector(
        self,
        session: Session,
        table: Table,
        query_embedding: list[float],
        limit: int,
        where: dict | None,
    ) -> list[dict]:
        distance_expr = table.c.embedding.l2_distance(query_embedding)
        stmt = (
            select(
                table.c.id,
                table.c.document,
                table.c.metadata_json,
                distance_expr.label("distance"),
            )
            .order_by(distance_expr)
            .limit(max(limit * 5, limit))
        )
        rows = session.execute(stmt).all()
        results: list[dict] = []
        for row in rows:
            metadata = dict(row.metadata_json or {})
            if not _metadata_matches(metadata, where):
                continue
            results.append(
                {
                    "id": row.id,
                    "document": row.document,
                    "metadata": metadata,
                    "distance": float(row.distance),
                }
            )
            if len(results) >= limit:
                break
        return results
