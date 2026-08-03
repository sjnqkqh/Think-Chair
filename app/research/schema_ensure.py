from sqlalchemy import text

from app.logging import get_logger

logger = get_logger(__name__)


def ensure_research_schema(engine) -> None:
    """create_all이 추가하지 못하는 research 관련 신규 컬럼을 SQLite에 보정한다."""
    with engine.begin() as connection:
        job_rows = connection.execute(
            text("PRAGMA table_info(research_jobs)")
        ).fetchall()
        job_columns = {row[1] for row in job_rows}
        if "claim_or_query" not in job_columns:
            connection.execute(
                text("ALTER TABLE research_jobs ADD COLUMN claim_or_query TEXT")
            )
            logger.info("research.schema_added_claim_or_query")

        comparison_rows = connection.execute(
            text("PRAGMA table_info(response_comparison_records)")
        ).fetchall()
        if not comparison_rows:
            return
        comparison_columns = {row[1] for row in comparison_rows}
        if "prepared_evidence_json" not in comparison_columns:
            connection.execute(
                text(
                    "ALTER TABLE response_comparison_records "
                    "ADD COLUMN prepared_evidence_json TEXT"
                )
            )
            logger.info("research.schema_added_prepared_evidence_json")
        if "consumed_at" not in comparison_columns:
            connection.execute(
                text(
                    "ALTER TABLE response_comparison_records "
                    "ADD COLUMN consumed_at DATETIME"
                )
            )
            logger.info("research.schema_added_consumed_at")
