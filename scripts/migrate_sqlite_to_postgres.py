"""SQLite 앱 DB·대화 이어가기를 Postgres로 옮긴다.

예:
  uv run python scripts/migrate_sqlite_to_postgres.py \\
    --sqlite ./rag_history.db \\
    --checkpoint-sqlite ./draftsmith_checkpoint.db \\
    --postgres-url postgresql+psycopg://thinkchair:thinkchair@localhost:5432/thinkchair

  # 대상에 이미 데이터가 있으면 비우고 다시 넣기
  uv run python scripts/migrate_sqlite_to_postgres.py \\
    --sqlite ./rag_history.db \\
    --checkpoint-sqlite ./draftsmith_checkpoint.db \\
    --postgres-url postgresql+psycopg://thinkchair:thinkchair@localhost:5432/thinkchair \\
    --replace

  uv run python scripts/migrate_sqlite_to_postgres.py --sqlite ./rag_history.db --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.core.config import settings
from app.migration.postgres_cutover import (
    TargetNotEmptyError,
    format_report,
    list_indexed_source_ids,
    migrate_sqlite_file_to_postgres,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=settings.DATA_ROOT / "rag_history.db",
        help="소스 앱 SQLite 파일 경로",
    )
    parser.add_argument(
        "--checkpoint-sqlite",
        type=Path,
        default=settings.DATA_ROOT / "draftsmith_checkpoint.db",
        help="대화 이어가기 SQLite 파일 경로",
    )
    parser.add_argument(
        "--skip-checkpoints",
        action="store_true",
        help="대화 이어가기 이전 생략",
    )
    parser.add_argument(
        "--checkpoints-only",
        action="store_true",
        help="앱 테이블은 건너뛰고 대화 이어가기만 이전",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.environ.get("DATABASE_URL", settings.DATABASE_URL),
        help="대상 Postgres URL (기본: DATABASE_URL / settings)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="스키마·복사를 하지 않고 소스 건수만 출력",
    )
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="스키마 생성 생략 (테이블이 이미 있을 때)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="대상 앱·대화 그래프 테이블을 비운 뒤 SQLite 내용으로 다시 채움",
    )
    parser.add_argument(
        "--list-reindex-targets",
        action="store_true",
        help="Postgres의 INDEXED research_sources id만 나열 (벡터 재인덱싱 대상)",
    )
    args = parser.parse_args(argv)

    if args.list_reindex_targets:
        ids = list_indexed_source_ids(args.postgres_url)
        print(f"indexed_sources={len(ids)}")
        for source_id in ids:
            print(source_id)
        print(
            "note: Chroma→pgvector 덤프 대신 원문 재인덱싱을 사용한다. "
            "재인덱싱 실행기는 후속 작업으로 둘 수 있다."
        )
        return 0

    if args.checkpoints_only and args.skip_checkpoints:
        print("--checkpoints-only 와 --skip-checkpoints 는 함께 쓸 수 없습니다.", file=sys.stderr)
        return 2

    try:
        report = migrate_sqlite_file_to_postgres(
            sqlite_path=args.sqlite,
            postgres_url=args.postgres_url,
            dry_run=args.dry_run,
            setup_schema=not args.skip_schema,
            replace_target=args.replace,
            checkpoint_sqlite_path=(
                None if args.skip_checkpoints else args.checkpoint_sqlite
            ),
            skip_checkpoints=args.skip_checkpoints,
            app_tables=not args.checkpoints_only,
        )
    except TargetNotEmptyError as exc:
        print(exc, file=sys.stderr)
        return 2

    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
