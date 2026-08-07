# 수평 확장(Scale-out) 병목 탐색

## 결론

- 현재 구조는 **단일 컨테이너 + `/data` 볼륨** 전제다. 복제본만 늘리는 수평 확장은 성립하지 않는다.
- 차단 요인은 API 코드보다 **로컬 저장소 다섯 곳**(앱 DB, 체크포인트, Chroma, 파일, 프로세스 내 백그라운드 태스크)이다.
- JWT 인증·조사 job 메타(DB)·`FileStorage` 추상화·채팅/조사 SSE 분리 계약은 이미 다중 인스턴스에 우호적이다.
- 이 문서는 탐색 결과만 담는다. 구현·마이그레이션 절차는 포함하지 않는다.

## 현재 아키텍처 (단일 노드 전제)

```text
Client
  → FastAPI (uvicorn 1프로세스, REST + Jinja + SSE)
      → SQLite          DATA_ROOT/rag_history.db
      → AsyncSqliteSaver DATA_ROOT/draftsmith_checkpoint.db
      → LocalFileStorage STORAGE_ROOT
      → Chroma PersistentClient CHROMA_ROOT
      → BackgroundTaskRegistry (asyncio.create_task)
            → run_research_job / 문서 생성
```

| 계층 | 현재 구현 | 핵심 경로 |
|------|-----------|-----------|
| API | FastAPI 단일 앱 | `app/main.py`, `app/api/endpoints/` |
| 앱 DB | SQLite + WAL | `app/core/database.py` |
| 그래프 상태 | LangGraph `AsyncSqliteSaver` | `app/graph/checkpointer.py`, `app/main.py` lifespan |
| 파일 | `LocalFileStorage` | `app/services/storage/local.py`, `app/core/storage.py` |
| 벡터 | Chroma `PersistentClient` | `app/research/evidence_index.py` |
| 백그라운드 | 프로세스 로컬 `asyncio.Task` | `app/services/background_tasks.py` |
| 인증 | JWT HS256 + httpOnly 쿠키 | `app/core/security.py` |
| 배포 | Compose 서비스 1개 + named volume `/data` | `docker-compose.yml` |

Compose·README는 SQLite DB, 체크포인트, 원고 파일, Chroma를 `think-chair-data` 볼륨에 보존한다고 명시한다. `replicas`, 공유 DB, 객체 스토리지, 워커 서비스는 없다.

## P0 — 복제본을 올리면 즉시 깨짐

### 1. 앱 DB = SQLite

- **경로:** `app/core/database.py` — `sqlite:///{DATA_ROOT}/rag_history.db`, WAL/`busy_timeout`만 설정.
- **왜 막힘:** 사용자·원고·채팅·조사 job 메타가 전부 여기 있다. 다중 writer·다중 호스트에서 잠금·손상·일관성 문제가 난다.

### 2. LangGraph 체크포인트 = SQLite 파일

- **경로:** `app/graph/checkpointer.py` (`AsyncSqliteSaver`), `app/main.py`에서 `DATA_ROOT/draftsmith_checkpoint.db`로 연다.
- **왜 막힘:** 대화·그래프 재개 상태가 프로세스·볼륨에 묶인다. 인스턴스 A가 쓴 체크포인트를 B가 못 읽으면 턴 이어가기·문서 생성이 깨진다. 화면 이력도 체크포인트에 의존한다(관련: `docs/reports/2026-07-28-reliability-and-dependency-review.md`).

### 3. 벡터 스토어 = 로컬 Chroma

- **경로:** `app/research/evidence_index.py` — `chromadb.PersistentClient(path=...)`. 설정 기본값은 `CHROMA_ROOT=./chroma_db` (`app/core/config.py`).
- **왜 막힘:** 인덱싱한 인스턴스와 검색하는 인스턴스가 다르면 근거가 누락된다. 파일 기반 Chroma는 다중 writer에 부적합하다.

### 4. 파일 스토리지 = 로컬 디스크

- **경로:** `app/services/storage/local.py` (`LocalFileStorage`), `app/core/storage.py`의 `get_file_storage()`(lru_cache 싱글톤). 인터페이스는 `app/services/storage/base.py`의 `FileStorage`.
- **왜 막힘:** 원고·조사 원문이 인스턴스 로컬(또는 단일 볼륨)에만 있다. 공유 NFS 등은 우회책일 뿐 잠금·일관성 이슈가 남는다.

### 5. 백그라운드 작업 = 프로세스 로컬 태스크

- **경로:** `app/services/background_tasks.py` (`asyncio.create_task`), 조사는 `app/services/research_job_service.py`에서 `background_tasks.start(execute_research_job(...))`, 문서 생성도 `app/services/chat_service.py`에서 동일 패턴.
- **왜 막힘:** job 생성 요청이 붙은 인스턴스에서만 실행된다. 그 프로세스가 죽으면 DB에 PENDING/RUNNING만 남고 다른 인스턴스가 가져가지 않는다. `ResearchJobContext.begin()`(`app/research/research_job_context.py`)은 단순 `mark_running`이며 분산 claim/lease·재시작 복구가 없다.

## P1 — 다중 인스턴스에서 어긋나거나 스케일 효과가 제한됨

### 6. SSE와 긴 작업의 프로세스 점유

- 채팅·조사 continue는 SSE다(`app/api/endpoints/chat.py`, `research.py`).
- 스펙상 채팅 SSE는 조사를 기다리지 않고 끊긴다(`docs/specs/2026-08-05-web-search-and-evidence-flow.md`). **세션 어피니티는 필수가 아니다.**
- 다만 LLM 스트리밍·조사 agent는 웹 프로세스의 CPU·연결·이벤트 루프를 점유한다. 큐 없이 복제만 하면 LLM 병목이 API와 같은 프로세스에 남는다.

### 7. 배포 토폴로지 = 단일 서비스

- `docker-compose.yml`에 `think-chair` 하나와 volume 하나만 있다. 로드밸런서·공유 스토어·워커 서비스 경로가 정의되어 있지 않다.

### 8. 프로세스 로컬 캐시 (차단 요인 아님)

- LLM 클라이언트 `_registry`(`app/llm/registry.py`), `get_file_storage` lru_cache는 인스턴스마다 중복 생성될 뿐이다. 기능 깨짐보다 자원 중복 수준이다.

## 이미 scale-out에 우호적인 부분

- **JWT 쿠키 인증** — 서버 세션 스토어가 없다. 시크릿만 인스턴스 간 공유하면 된다.
- **조사 job 메타가 DB에 있음** — 큐만 외부화하면 worker가 `job_id`로 실행할 수 있다.
- **`FileStorage` 추상 인터페이스** — 원격 객체 스토리지 구현으로 교체할 자리가 있다.
- **채팅↔조사 분리(SSE 끊고 폴링 후 continue)** — sticky 세션 의존을 줄인 계약이다.
- **엔드포인트 thin / 서비스 분리** — 워커 프로세스로 옮길 때 호출 경계가 비교적 명확하다.

## 구조적 전환 순서 (의존 순서, 구현 아님)

P0를 건너뛰고 복제본만 늘리면 데이터 분열·유실 job·근거 누락이 난다. 아래는 의존 관계만 적은 순서다.

1. **공유 앱 DB** — SQLite → Postgres(또는 동등 RDB). 도메인 메타의 전제.
2. **공유 체크포인트** — LangGraph용 공유 checkpointer로 교체. 대화 연속성.
3. **공유 객체 스토리지** — `FileStorage` 구현을 원격으로. 원고·조사 원문.
4. **공유 벡터 스토어** — 로컬 Chroma → 원격/관리형 또는 동등. 인덱싱·검색 분리.
5. **작업 큐 + 워커** — `BackgroundTaskRegistry`를 큐 발행으로 바꾸고 API/워커 분리. job claim/lease·재시작 복구.
6. **그다음** API N + Worker M 수평 복제와 로드밸런서. 읽기 가속 캐시는 SoT가 아니라 후순위 계층으로만 둔다.

## 관련 문서

- `docs/reports/2026-07-28-reliability-and-dependency-review.md` — 단일 노드에서의 백그라운드·체크포인트·메시지 이력 기준
- `docs/specs/2026-08-05-web-search-and-evidence-flow.md` — 채팅 SSE와 조사 job 분리 계약
- `docs/plans/agentic-research-rag/README.md` — 외부 작업 대기열을 “필요할 때”로 미룬 초기 판단
