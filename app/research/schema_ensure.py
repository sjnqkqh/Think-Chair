from sqlalchemy import text

from app.logging import get_logger

logger = get_logger(__name__)


def ensure_research_schema(engine) -> None:
    """create_all이 추가하지 못하는 research_jobs 신규 컬럼을 SQLite에 보정한다."""
    with engine.begin() as connection:
        rows = connection.execute(text("PRAGMA table_info(research_jobs)")).fetchall()
        columns = {row[1] for row in rows}
        if "claim_or_query" not in columns:
            connection.execute(
                text("ALTER TABLE research_jobs ADD COLUMN claim_or_query TEXT")
            )
            logger.info("research.schema_added_claim_or_query")
