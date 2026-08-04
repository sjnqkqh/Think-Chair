# Think Chair

LLM에 의존하던 시절, 우리는 편리함과 함께 주도성 상실을 경험했습니다. 우리는 개발자임에도, 스스로 무언가를 만들고 있다는 감각은 점점 흐려졌습니다.

**Think Chair**는 그 반대 방향으로 움직이는 프로그램입니다. 답을 대신 내놓는 AI가 아니라, 끊임없이 질문을 던지며 사용자의 생각을 끌어내는 AI를 지향합니다.

사용자가 글감이나 주제를 제시하면 AI는 관련 질문을 만들고, 사용자의 답변에서 논리적 빈틈과 불명확한 지점을 찾아 더 깊은 질문으로 이어갑니다. 이 과정은 사용자가 안다고 생각했던 개념과 아직 설명하지 못하는
개념을 구분할 때까지 반복됩니다.

Think Chair는 개발자가 자신이 가진 지식의 밑바닥을 직접 마주하고, AI의 질문에 최대한의 근거를 갖춘 의견을 내며, 피드백 루프를 거쳐 더 깊은 수준의 지식을 습득하도록 돕기 위해 만들어졌습니다.

## 무엇을 하는가

Think Chair는 FastAPI 기반 **AI 사고 훈련 및 글쓰기 협업 워크스페이스**입니다. 로그인한 사용자가 주제와 글의 유형을 정하면, AI가 교수처럼 질문하고 피드백하며 사용자의 생각을 구조화합니다.
충분한 대화가 쌓이면 사용자는 개요를 만들거나, 지금까지의 대화를 바탕으로 마크다운 원고를 생성하고 버전으로 저장할 수 있습니다.

딥다이브·수업 자료 컨셉에서는, 사용자가 일반론·수치 주장을 하면 Agentic RAG가 근거를 모아 다음 턴 대화에 주입합니다.
핵심은 "AI가 바로 써주는 글"이 아니라 "사용자가 설명할 수 있을 때까지 AI가 되묻고, 구체화하는 과정"입니다.

## 주요 기능

- 주제 기반 워크스페이스 생성
- 딥다이브, 회고, 에세이, TIL, 수업 자료 컨셉 지원
- LangGraph 기반 대화 흐름 제어
- 질문, 피드백, 개요 생성, 탈고 요청을 의도별 노드로 라우팅
- 딥다이브·수업 자료에서 일반론 감지 시 비동기로 웹에서 근거 자료 조사
- Brave Search·페이지 수집·Chroma 인덱싱 후 다음 턴 근거 주입
- 대화 히스토리를 바탕으로 마크다운 개요와 최종 원고 생성
- 생성된 원고 버전 저장 및 다운로드
- JWT 쿠키 기반 로그인/회원가입
- LangSmith / LangFeather 추적 연동
- 서비스 성장 관측용 절대 Judge 평가 (일반론 50사례)

## 사용 흐름

1. 사용자가 워크스페이스에서 주제와 컨셉을 선택해 원고를 생성합니다.
2. AI가 주제에 대한 첫 질문을 던집니다.
3. 사용자는 자신의 경험, 이해, 주장, 근거를 답변합니다.
4. AI는 답변의 비약, 모호한 표현, 근거 부족을 짚고 더 구체적인 질문을 이어갑니다.
5. (딥다이브·수업 자료) 일반론·수치 주장이 감지되면, 대화와 별도로 웹에서 근거 자료를 찾아 두고, 다음 답변에 반영합니다.
6. 사용자는 필요할 때 피드백을 요청해 현재까지의 논리와 재료를 점검합니다.
7. 충분한 대화가 쌓이면 개요를 생성합니다.
8. 최종적으로 지금까지의 대화와 개요를 바탕으로 마크다운 원고를 탈고하고 버전으로 저장합니다.

## 기술 스택

| 영역     | 기술                                                    |
|--------|-------------------------------------------------------|
| 서버     | FastAPI, Jinja2, htmx, Alpine.js                      |
| 데이터    | SQLAlchemy, SQLite                                    |
| LLM 흐름 | LangGraph `StateGraph`, LangGraph SQLite Checkpointer |
| LLM 연동 | `langchain-openai` 호환 DeepSeek 설정                     |
| 웹 조사   | Brave Search, ChromaDB, OpenAI embeddings             |
| 인증     | JWT 쿠키                                                |
| 저장소    | 로컬 파일 스토리지 기반 마크다운 버전 저장                              |
| 추적     | LangSmith, LangFeather                                |
| 테스트    | pytest, pytest-asyncio                                |

## 프로젝트 구조

```text
app/
├── main.py                  # FastAPI 앱 조립, LangGraph 체크포인터/그래프 초기화
├── api/endpoints/           # API 라우터: auth, manuscripts, chat, research
├── pages/                   # HTML 페이지 라우터: auth, workspace, chat
├── templates/               # Jinja2 템플릿
├── graph/                   # LangGraph 상태 머신, 노드, 라우터, 프롬프트
│   ├── builder.py            # opening/say/feedback/outline/generate_document_from_conversation 흐름 구성
│   ├── state.py              # GraphState, UserAction, NewPaper 타입
│   ├── nodes/                # 대화, 피드백, 개요, 탈고, 저장 노드
│   └── prompts/              # persona/phase/concept/constraint 프롬프트 조합
├── research/                # 웹 조사: 필요 여부 판단, 검색·수집·인덱싱, 근거 주입
├── evaluation/              # 응답 비교·서비스 성장 Judge 실행기
├── models/                  # SQLAlchemy 모델
├── repositories/            # DB 접근 계층
├── schemas/                 # Pydantic 스키마
├── services/                # 인증, 채팅, 원고, 웹 조사, 저장소 비즈니스 로직
└── core/                    # 설정, DB 세션, 보안, 예외 처리, 필터 등 공통 유틸

tests/                       # pytest 테스트
docs/plans/                  # Agentic RAG·평가 설계 문서
pr-docs/                     # 변경 이력과 PR 문서
artifacts/                   # 평가 리포트 출력
```

## LangGraph 흐름

Think Chair의 대화는 `app/graph/builder.py`의 상태 머신으로 실행됩니다.

- `opening`: 새 원고의 첫 대화에서 주제별 오프닝 질문 생성
- `say`: 일반 대화와 사고 확장 질문 (준비된 근거가 있으면 함께 반영)
- `feedback`: 지금까지의 내용에 대한 논리 점검과 보완 질문
- `outline`: 대화를 바탕으로 목차와 핵심 문장 생성
- `generate_document_from_conversation`: 대화를 바탕으로 저장 가능한 마크다운 원고 생성
- `chinese_prevent`: 한자/중국어 혼입 정제
- `make_new_paper`: 생성된 개요 또는 원고를 버전으로 저장

사용자 메시지는 먼저 라우터 프롬프트에서 `say / feedback / outline / generate_document` 중 하나로 분류되고, 각 노드의 결과는 LangGraph SQLite
Checkpointer에 대화 상태로 누적됩니다.

웹 조사가 필요한지는 대화 의도(`say` / `feedback` 등)와 별도로 판단합니다.  
딥다이브·수업 자료에서만 켜지며, 검색과 자료 수집은 채팅 응답을 기다리지 않고 백그라운드에서 진행됩니다.

## 웹 조사 (Agentic RAG)

딥다이브·수업 자료 원고에서 사용자가 일반론·수치 주장을 하면, AI가 그 주장을 검증할 자료를 웹에서 찾아 둡니다. 대화는 끊기지 않고 이어지고, 자료가 준비되면 이후 답변에 근거로 쓰입니다.

흐름은 대략 다음과 같습니다.

1. 서버가 “이 주장에는 웹 근거가 필요하다”고 표시합니다.
2. 화면(또는 API 호출)이 백그라운드 웹 조사를 시작합니다. 원고마다 최대 5번까지입니다.
3. Brave Search로 관련 페이지를 찾고, 내용을 잘라 Chroma에 저장합니다.
4. 다음 `say` / `feedback` 답변을 만들 때 그 자료를 불러와 참고합니다.

TIL·에세이·회고에서는 같은 종류의 주장이 나와도 웹 조사를 시작하지 않습니다.

설계·핸드오프: `docs/plans/agentic-research-rag/`

## 환경 설정

프로젝트 루트에 `.env` 파일을 생성합니다.

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
BRAVE_SEARCH_API_KEY=your_brave_search_api_key
OPENAI_API_KEY=your_openai_api_key

JWT_SECRET=change-this-in-production
JWT_TTL_HOURS=24
STORAGE_ROOT=./storage
CHROMA_ROOT=./chroma_db

# 선택: 서비스 성장 Judge (비우면 DEEPSEEK_MODEL 사용)
SERVICE_GROWTH_JUDGE_MODEL=

# 선택: LangSmith 추적
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_PROJECT=think-chair

# 선택: local LangFeather (collector를 127.0.0.1:4319에서 실행한 뒤)
LANGFEATHER_ENABLED=true
LANGFEATHER_ENDPOINT=http://127.0.0.1:4319
```

## 실행

```bash
uv sync
uvicorn app.main:app --reload
```

- 워크스페이스: `http://localhost:8000/workspace`
- API 문서: `http://localhost:8000/docs`

## Docker

Docker Compose로 이미지를 빌드하고 호스트의 9000번 포트에서 실행합니다. `.env`에
`DEEPSEEK_API_KEY`와 운영용 `JWT_SECRET`을 설정한 뒤 실행하세요.

```bash
docker compose up --build -d
```

- 워크스페이스: `http://localhost:9000/workspace`
- API 문서: `http://localhost:9000/docs`

앱 로그와 종료는 다음 명령으로 확인합니다.

```bash
docker compose logs -f
docker compose down
```

Compose는 SQLite DB, LangGraph 체크포인트, 원고 파일과 Chroma 검색 자료를
`think-chair-data` named volume에 보존합니다. 볼륨까지 삭제하려면
`docker compose down -v`를 사용합니다.

기존 Docker CLI 실행 방법:

```bash
docker build -t think-chair .
docker run --rm -p 8000:8000 --env-file .env \
  -e DATA_ROOT=/data -e STORAGE_ROOT=/data/storage \
  -v "$(pwd)/data:/data" think-chair
```

컨테이너 내부 포트는 8000이며, Compose가 이를 호스트의 9000번 포트로 연결합니다.

## API

```text
POST   /api/auth/signup
POST   /api/auth/login
POST   /api/auth/logout

POST   /api/manuscripts
GET    /api/manuscripts
GET    /api/manuscripts/{manuscript_id}
GET    /api/manuscripts/{manuscript_id}/versions/{version_id}/download
POST   /api/manuscripts/{manuscript_id}/finalize?version_id=...

POST   /api/chat/{manuscript_id}/message

# 웹 조사 시작 / 진행 조회 / 취소
POST   /api/research/jobs
GET    /api/research/jobs/{id}?manuscript_id=...
POST   /api/research/jobs/{id}/cancel?manuscript_id=...
```

## 평가

서비스가 같은 일반론 세트에 대해 얼마나 성장했는지 관측하려면 절대 Judge 실행기를 사용합니다. 배포 게이트가 아니라 시계열 관측용입니다.

```bash
uv run python -m app.evaluation.run_service_growth_eval
# 선택: --limit 5 --phase say
```

- 사례: `tests/evaluation/service_growth_cases.json` (일반론 50)
- 산출: `artifacts/service_growth_eval/` (JSON·마크다운)
- Judge 축: 참고 제안, 주장 날카로움, 지식 심화, 대화 적합, 다음 단계 명확성, overall (0~100 연속 척도)
- 계획: `docs/plans/agentic-research-rag/11-rag-judge-corpus-plan.md`

근거 유무 pairwise 비교(개발용 하네스)는 별도입니다.

```bash
uv run python -m app.evaluation.run_response_comparison
```

## 테스트

```bash
uv run pytest
uv run ruff check app tests
```

`tests/`는 인증, 원고 서비스, LangGraph 노드와 빌드, 채팅 API, 웹 조사, 워크스페이스 페이지, 한자/중국어 필터, 로컬 스토리지, 평가 계약을 검증합니다.

외부 네트워크가 필요한 live 검사는 기본 테스트에서 건너뜁니다. 개발자가 직접 확인할 때만 다음과 같이 실행합니다.

```bash
RUN_LIVE_WEB_TESTS=1 uv run pytest \
  tests/integration/research/test_live_page_compatibility.py

# Brave/OpenAI 실호출 + 임시 DB·Chroma 격리 E2E
uv run pytest tests/e2e/test_live_research_conversation.py
```

## License

This project is licensed under the [MIT License](LICENSE).
