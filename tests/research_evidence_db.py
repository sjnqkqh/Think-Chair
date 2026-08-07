"""테스트에서 근거 인덱스용 DB 스키마를 미리 만든다."""

from app.core.database import build_engine
from app.core.schema_bootstrap import create_app_schema
from app.research.evidence_index import ResearchEvidenceIndex


def open_prepared_evidence_index(
    database_url: str,
    *,
    embedding_model: str,
    embedding_dimension: int,
    chunk_schema_version: str,
) -> ResearchEvidenceIndex:
    engine = build_engine(database_url)
    create_app_schema(
        database_url,
        engine,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        chunk_schema_version=chunk_schema_version,
    )
    engine.dispose()
    return ResearchEvidenceIndex(
        database_url,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        chunk_schema_version=chunk_schema_version,
    )
