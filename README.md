# Draftsmith

FastAPI 기반 **Draftsmith (AI 글쓰기 협업 워크스페이스)** 서버입니다. 로그인한 사용자가 원고(기술 딥다이브, 회고, 에세이, TIL, 강의자료)를 주제로 개설하고, 채팅으로 AI와 대화하며 개요 → 초고 → 탈고 단계를 거쳐 마크다운 원고를 생성·확정하는 LangGraph 기반 워크스페이스입니다.

## 기술 스택

| 영역 | 기술 |
|------|------|
| 서버 | FastAPI, Jinja2 + htmx, SQLAlchemy (SQLite) |
| LLM | LangGraph `StateGraph`, `llm_registry`를 통한 모델 선택(기본 DeepSeek) |
| 인증 | JWT 쿠키 기반 (`app/core/security.py`, `app/core/auth_deps.py`) |
| 대화 상태 저장 | LangGraph SQLite Checkpointer (`draftsmith_checkpoint.db`) |
| 추적 | LangSmith |

## 프로젝트 구조

```
app/
├── main.py                  # FastAPI 앱 조립, lifespan에서 LangGraph 체크포인터/그래프 초기화
├── api/endpoints/           # API: auth, manuscripts
├── pages/                   # HTML 페이지 라우터 (Jinja2 + htmx)
│   ├── auth_pages.py         # 로그인/회원가입 화면
│   ├── workspace_pages.py    # 워크스페이스 화면
│   └── chat_pages.py         # 채팅 메시지 처리 (htmx partial 응답)
├── graph/                   # LangGraph 정의
│   ├── builder.py            # StateGraph 노드/엣지 구성
│   ├── state.py              # DraftsmithState, UserAction, PendingVersion 타입
│   ├── checkpointer.py       # SQLite AsyncSqliteSaver 팩토리
│   ├── llm_registry.py       # 모델 이름 → LLM 인스턴스 매핑
│   ├── nodes/                # router, converse, feedback, outline, draft, polish,
│   │                          # chinese_prevent, persist_version, finalize
│   └── prompts/              # phase/concept/persona/constraint 조합으로 시스템 프롬프트 생성
├── models/                  # SQLAlchemy 모델 (User, Manuscript, ManuscriptVersion)
├── repositories/            # DB 접근 계층 (manuscript_repo)
├── schemas/                 # Pydantic 요청/응답 스키마
├── services/                # 비즈니스 로직 (얇은 엔드포인트 원칙: 로직은 전부 여기)
│   ├── auth_service.py, manuscript_service.py, chat_service.py
│   └── storage/              # 원고 마크다운 파일 저장 추상화 (local 구현)
├── core/                    # 설정, DB 세션, 예외 처리, JWT, 한자 필터 등 공통 유틸
└── templates/               # Jinja2 템플릿 (auth/, workspace/)
tests/                       # pytest 테스트
prompt-sample/               # 원고 컨셉별 프롬프트 마크다운 원본(체크리스트/품질기준 등)
```

## 환경 설정

`.env.example`을 참고해 프로젝트 루트에 `.env` 파일을 생성합니다.

```env
# 사용하는 LLM — 기본값이 비어 있으면 실제 호출 시 인증 실패
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 인증 — 운영 배포 전 반드시 교체
JWT_SECRET=dev-secret-change-me

# 선택 — LangSmith 추적
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=your_project_name
```

## 실행

```bash
# 의존성 설치 (uv 권장)
uv sync

# 서버 실행
uvicorn app.main:app --reload
```

- 워크스페이스: `http://localhost:8000/workspace` (로그인 필요, 없으면 회원가입 유도)
- API 문서: `http://localhost:8000/docs`

## 흐름 개요

1. 사용자가 워크스페이스에서 원고(주제 + 컨셉 + 독자 수준)를 생성하면 `/workspace/{manuscript_id}`로 이동한다.
2. 사이드바 버튼 또는 자유 채팅 입력이 `POST /api/chat/{manuscript_id}/message`로 전송된다.
3. `ChatService.run()`이 LangGraph(`build_graph`)를 `thread_id=manuscript_id`로 실행한다. 대화 이력은 별도 테이블 없이 LangGraph SQLite 체크포인터가 유일한 소스다.
4. `router_node`가 분류 프롬프트(`CLASSIFIER`)로 사용자 의도를 `say / inspect / feedback / outline / draft / polish / finalize` 중 하나로 분류하고, 조건부 엣지로 해당 노드로 라우팅한다.
5. `outline_node` / `draft_node` / `polish_node`는 컨셉·단계·독자 수준에 맞는 시스템 프롬프트(`build_system_prompt`)로 LLM을 호출해 마크다운 콘텐츠를 만들고, 채팅 메시지에는 완료 안내만 남긴 채 `pending_version`에 결과를 담는다.
6. 모든 생성/대화 노드는 공통으로 `chinese_prevent_node`를 거쳐 한자(중국어) 혼입을 정제한 뒤, `pending_version`이 있으면 `persist_version_node`로 이어진다.
7. `persist_version_node`가 마크다운을 파일 스토리지에 저장하고 `ManuscriptVersion` row(kind, revision, storage_key)를 커밋한다.
8. 응답 htmx partial(`_chat_turn.html`)이 채팅 메시지 2개와 함께 `_version_update.html`을 포함하는데, 여기서 `hx-swap-oob`로 우측 사이드바의 버전 목록(`#version-list`)에 새 버전을 out-of-band로 추가한다.
9. 사용자는 버전별로 다운로드하거나(`GET /api/manuscripts/{id}/versions/{version_id}/download`), 하나를 확정(`POST /api/manuscripts/{id}/finalize?version_id=...`)할 수 있다.

## 원고 컨셉(ConceptType)

`tech_deepdive`(기술 딥다이브), `retrospective`(회고), `essay`(에세이), `til`(TIL), `teaching`(강의자료) — 각 컨셉의 프롬프트 원본은 `prompt-sample/`에 있으며, `app/graph/prompts/concepts/`에서 로드해 시스템 프롬프트를 조합한다.

## API

```
POST   /api/auth/signup                                  # 회원가입, JWT 쿠키 발급
POST   /api/auth/login                                   # 로그인
POST   /api/auth/logout                                   # 로그아웃

POST   /api/manuscripts                                   # 원고 생성 (topic, concept, audience_level)
GET    /api/manuscripts                                   # 내 원고 목록
GET    /api/manuscripts/{manuscript_id}                   # 원고 상세
GET    /api/manuscripts/{manuscript_id}/versions/{version_id}/download   # 버전 마크다운 다운로드
POST   /api/manuscripts/{manuscript_id}/finalize?version_id=...          # 버전 확정

POST   /api/chat/{manuscript_id}/message                  # 채팅 메시지 전송 (htmx partial 응답)
```

## 테스트

```bash
pytest
```

`tests/`는 인증, 원고 서비스, LangGraph 노드·빌드, 채팅 API, 워크스페이스 페이지, 한자 필터, 스토리지를 커버합니다.
