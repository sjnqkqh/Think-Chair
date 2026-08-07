# SQLite → Postgres 컷오버

기존 단일 노드 볼륨의 SQLite 앱 DB를 Compose Postgres로 옮긴다.
근거 벡터(Chroma)와 LangGraph checkpointer SQLite는 **덤프 이전하지 않는다**.

## 전제

- 단계1 코드(앱 DB·checkpointer·pgvector 런타임)가 이미 반영된 환경
- 원본 `rag_history.db` 백업을 남겨 둔다
- 대상 Postgres는 Compose `db` 서비스 (또는 동등 URL)

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

3. 스키마 재현 + 데이터 복사

```bash
uv run python scripts/migrate_sqlite_to_postgres.py \
  --sqlite /path/to/rag_history.db \
  --postgres-url postgresql+psycopg://thinkchair:thinkchair@localhost:5432/thinkchair
```

4. 벡터 재인덱싱 대상 확인

```bash
uv run python scripts/migrate_sqlite_to_postgres.py --list-reindex-targets
```

`INDEXED`인 `research_sources`는 원문(`storage_key`)을 기준으로 pgvector에 다시 넣어야 한다.
Chroma 디렉터리 덤프 이전은 제공하지 않는다.

5. 대화 이어가기

- `draftsmith_checkpoint.db`는 이전하지 않는다
- Postgres checkpointer는 스키마만 만들고 비운다
- 채팅 **화면 이력**은 앱 DB `chat_messages` 행을 따른다
- 그래프 중간 상태 재개는 새 대화부터 유효하다

## 롤백

- 앱 `DATABASE_URL`을 다시 SQLite로 돌리지 않는 것이 기본이다 (단계1 이후 런타임은 Postgres)
- 데이터가 깨졌으면 Postgres 볼륨을 비우고, 보관한 `rag_history.db`로 3을 다시 실행한다

## 런타임 ALTER

앱 기동 코드에서 `ALTER TABLE`로 스키마를 고치지 않는다.
스키마는 이 스크립트의 `ensure_postgres_schema`(ORM `create_all` + `vector` + checkpointer `setup`)로만 재현한다.
