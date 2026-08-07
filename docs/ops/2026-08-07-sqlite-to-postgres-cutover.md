# SQLite → Postgres 이전

기존 단일 노드 볼륨의 SQLite 앱 DB를 Compose Postgres로 옮긴다.
근거 벡터(Chroma)와 대화 그래프용 SQLite 파일은 **통째로 복사하지 않는다**.

## 역할 구분

| 일 | 담당 |
|----|------|
| 테이블·확장 **처음 만들기** | 이전/초기화 **파이썬 스크립트** (`create_app_schema` 등) |
| 이미 있는 DB의 **구조 변경** | 개발자가 별도 SQL/마이그레이션으로 |
| 서버 기동 | 이미 있는 테이블만 사용. 스키마를 만들지 않음 |
| SQLite → Postgres **행 복사** | 같은 이전 스크립트, 한 번 |

## 전제

- 원본 `rag_history.db` 백업을 남겨 둔다
- 대상은 Compose `db` (또는 동등 URL)
- 앱을 올리기 **전에** 스키마 스크립트를 한 번 돌린다

## 절차

1. Postgres 기동

```bash
docker compose up -d db
```

2. dry-run (소스 건수만)

```bash
uv run python scripts/migrate_sqlite_to_postgres.py \
  --sqlite /path/to/rag_history.db \
  --postgres-url postgresql+psycopg://thinkchair:thinkchair@localhost:5432/thinkchair \
  --dry-run
```

3. 스키마 생성 + 데이터 복사

```bash
uv run python scripts/migrate_sqlite_to_postgres.py \
  --sqlite /path/to/rag_history.db \
  --postgres-url postgresql+psycopg://thinkchair:thinkchair@localhost:5432/thinkchair
```

이 단계에서 `vector` 확장, 앱 테이블, 근거 검색 테이블, 대화 그래프 저장 테이블을 만든다.

4. 벡터 재인덱싱 대상 확인

```bash
uv run python scripts/migrate_sqlite_to_postgres.py --list-reindex-targets
```

`INDEXED`인 조사 원문은 저장된 파일을 기준으로 벡터를 다시 넣어야 한다.

5. 대화 이어가기

- 옛 대화 그래프 SQLite 파일은 이전하지 않는다
- Postgres 쪽 그래프 저장은 비운 채로 둔다
- 채팅 **화면 이력**은 앱 DB `chat_messages`를 따른다

## 롤백

- Postgres 볼륨을 비우고, 보관한 `rag_history.db`로 3을 다시 실행한다
