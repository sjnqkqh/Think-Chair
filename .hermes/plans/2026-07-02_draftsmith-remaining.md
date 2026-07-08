# Draftsmith(초공) 잔여 작업 계획 (T14~T20)

> **기준 시점:** 2026-07-02
> **원본 계획:** `.hermes/plans/2026-07-01_142505-draftsmith.md` (T1~T21 전체 스펙)
> **이 문서의 목적:** 완료된 T1~T13/T21은 요약만 남기고, 아직 손대지 않은 T14~T20을 실제 코드베이스 현재 상태를 기준으로 매우 상세하게 재작성한다. 원본 계획서의 코드 스니펫은 설계 당시 가정(예: `hanja_guard`, `SqliteSaver`, `ChatAnthropic`, `haiku` 모델 별칭)을 담고 있어 실제 구현과 이름이 다른 부분이 있다 — 이 문서는 그 괴리를 전부 실제 이름으로 교정했다.
> **불변 제약:** git commit 금지(사용자가 직접 리뷰 후 커밋). 태스크별로 `uv run pytest -q`와 `uv run ruff check app tests`를 통과시킨 뒤 다음 태스크로 넘어간다.
> **2026-07-02 설계 정정 반영(중요):** 우측 패널 버튼은 `/api/generate/{action}` 같은 별도 엔드포인트를 호출하지 않는다. ChatGPT의 추천 질문 버튼처럼, 클릭 시 해당 문구가 **일반 채팅과 동일한 단일 채널**(`/api/chat/{manuscript_id}/message`)로 전송된다. `user_action`은 더 이상 호출부가 지정하는 값이 아니라, `router_node`가 매 메시지마다 LLM으로 의도를 분류해 채우는 값이다. 이 정정에 따라 아래 T15/T16은 폐기되었고, T14의 우측 버튼 설계도 수정되었다 — 각 절 본문 참조.

---

## 0. 완료된 작업 요약 (T1~T13, T21, T10.5)

| 태스크 | 내용 | 비고 |
|---|---|---|
| T1 | 프로젝트 부트스트랩, 의존성(fastapi, langgraph, langchain-openai 등) 추가 | |
| T2 | `app/core/config.py` — `Settings`(pydantic-settings), `DEEPSEEK_*`, `STORAGE_ROOT`, `BASE_DIR` | Anthropic이 아니라 **DeepSeek(`ChatOpenAI` 호환 엔드포인트)** 로 구현됨 |
| T3 | 한자 필터 → `app/core/chinese_filter.py` (`contains_chinese`, `sanitize_chinese`) | 세션 중 `hanja_filter` → `chinese_filter`로 전면 개명 |
| T4 | `app/core/database.py` — `Base`, `engine`, `SessionLocal`, `get_database_session` | Alembic 대신 `Base.metadata.create_all()`로 단순화 |
| T5 | `app/models/user.py`, `app/core/security.py` (bcrypt/JWT) | |
| T6 | `app/api/endpoints/auth.py`, `app/pages/auth_pages.py`, `templates/auth/{signup,login}.html` | 쿠키명 `access_token`, `httponly=True, samesite="lax"` |
| T7 | `app/core/auth_deps.py::require_user` | `UnauthorizedError`(401) 사용, `app/core/exceptions.py` 계층 존재 |
| T8 | `app/models/manuscript.py`(`Manuscript`, `ManuscriptVersion`), `app/repositories/manuscript_repo.py`, `app/api/endpoints/manuscripts.py` | 현재 라우트: `POST/GET /api/manuscripts`, `GET /api/manuscripts/{id}` 3개만 존재. `/versions`, `/finalize`는 **아직 없음** (T17 대상) |
| T9 | `app/services/storage/base.py`(`FileStorage` ABC), `local.py`(`LocalFileStorage`) | `settings.STORAGE_ROOT` 기준 저장 |
| T10 | `app/graph/llm_registry.py`, `app/graph/prompts/**` | `bootstrap(settings)`가 `"default"` 별칭으로 `ChatOpenAI` 등록 |
| T10.5 | 컨셉별 `generate.md`/`checkpoint.md`/`purpose` 3종 분리, `phases/*.py` 컨셉 편향 문구 제거 | `tests/test_prompt_builder.py` 통과 |
| T11 | `app/graph/state.py`, `app/graph/nodes/*.py`, `app/graph/builder.py`, `app/graph/checkpointer.py` | 노드 9개: router/converse/feedback/outline/draft/polish/finalize/**chinese_prevent**/persist_version. 체크포인터는 `AsyncSqliteSaver`(비동기, `async with`) |
| T12 | `tests/conftest.py::fake_llm` fixture(`FakeListChatModel`), `tests/test_graph_nodes.py` | |
| T13 | `app/services/chat_service.py::ChatService.run()`, `app/api/endpoints/chat.py`... 는 실제로는 `app/pages/chat_pages.py`에 구현됨(주의: JSON API가 아니라 HTML partial 반환) | `POST /api/chat/{manuscript_id}/message` → `templates/workspace/_message.html` 렌더 |
| T11.5 | `app/graph/nodes/router.py`, `app/graph/prompts/classifier.py`(신규), `app/graph/state.py`, `app/services/chat_service.py`, `app/pages/chat_pages.py` | **2026-07-02 설계 정정 반영.** `router_node`가 no-op에서 LLM 기반 의도 분류기로 교체됨: 마지막 `HumanMessage`를 `CLASSIFIER` 프롬프트로 분류해 `say/inspect/feedback/outline/draft/polish` 중 하나를 `state["user_action"]`에 채움(매칭 실패 시 `"say"`로 폴백). `finalize`는 분류 대상에서 제외(특정 version_id가 필요한 별개 액션이라 자연어 분류에 부적합, 별도 유지). `ChatService.run()`에서 `user_action` 파라미터 제거, `user_message`만 받음. `chat_pages.py`의 `user_action="say"` 하드코딩 제거. `state.py`의 `user_action` 타입은 `UserAction \| None`으로 변경. `tests/test_graph_nodes.py`에 분류 성공/폴백 테스트 2건 추가 |

세션 중 있었던 추가 결정 사항(모두 확정, 재론의 불필요):
- `draftsmith_ckpt.db` → `draftsmith_checkpoint.db`, `hanja_guard` → `chinese_prevent` 전면 개명 완료.
- LangGraph 학습용 한글 주석이 `app/graph/**`, `app/services/chat_service.py`에 다수 추가되어 있음 — **사용자가 커밋 전 직접 제거 예정**이므로 향후 작업에서 이 주석들을 "정리"할 필요 없음(그대로 둘 것).
- ~~`router_node`(no-op)는 의도적으로 유지하기로 결정됨(제거하지 않음).~~ **정정(2026-07-02):** `router_node`는 더 이상 no-op이 아니다. LLM 기반 의도 분류기로 교체됨(T11.5 참조).
- `builder.py`는 `add_node`를 모두 등록한 뒤 `add_edge(START, "router")`, 그다음 조건부 엣지 순으로 정렬됨(가독성 이유로 확정된 순서, 임의 변경 금지).

**중요한 원본 계획과의 구조적 차이 (T14~T20 작성 시 반드시 반영):**
1. **ChatMessage 테이블이 없다.** 원본 계획 2.1절의 `ChatMessage`(SQL 이중 저장) 모델은 구현되지 않았다. 현재 대화 이력은 오직 LangGraph `AsyncSqliteSaver` 체크포인터에만 존재한다. T14(워크스페이스 페이지)에서 "새로고침 시 대화 이력 표시"가 필요하다면, DB 테이블이 아니라 **`graph.aget_state(config)`로 체크포인트에서 `messages`를 읽어와야 한다.**
2. **`/api/chat/...` 라우트가 `app/api/endpoints/`가 아니라 `app/pages/chat_pages.py`에 있다.** HTML partial을 반환하기 때문 — `CLAUDE.md`의 "HTML 반환 라우트는 `app/pages/`" 규칙에 따른 것. **T15~T17의 신규 라우트(`/api/generate/*`, `/api/manuscripts/{id}/finalize`)도 반환 타입에 따라 배치를 재검토해야 한다:**
   - `/api/generate/*`: 원본 계획은 HTML partial을 반환하도록 설계했으므로 → **`app/pages/generate_pages.py`**에 둔다 (`app/api/endpoints/`가 아님).
   - `/api/manuscripts/{id}/finalize`: JSON만 반환하면 `app/api/endpoints/manuscripts.py`에 추가해도 되지만, 우측 사이드바 상태를 HTMX로 갱신하려면 partial을 반환해야 하므로 이 경우도 `app/pages/`행이 맞다. **T17에서 응답 형태를 먼저 확정하고 그에 맞는 위치를 정한다(아래 T17 상세 참조).**
3. **`get_chat_service(request)` 패턴**이 이미 `chat_pages.py`에 있다(`request.app.state.chat_service`). 신규 라우트도 이 함수를 재사용한다(중복 정의 금지).
4. 프롬프트/에러 처리: `NotFoundError`, `UnauthorizedError`는 `app/core/exceptions.py` + `app/core/error_handlers.py`가 자동으로 HTTP 응답으로 변환하므로, 라우트에서 `try/except`로 감쌀 필요 없음 — `manuscript_repo.get_owned()`가 `None`이면 `manuscript_service.get_manuscript()`가 이미 `NotFoundError`를 던진다.
5. **(2026-07-02 정정, 원본 계획 이후 추가 확정)** `/api/generate/{action}` 형태의 액션별 전용 라우트는 만들지 않는다. 우측 패널 버튼은 액션 필드를 실어 보내는 특수 요청이 아니라, 자연어 문구를 채팅과 동일한 단일 채널(`/api/chat/{manuscript_id}/message`)로 전송하는 UX 장치일 뿐이다. 실제 phase 판별은 `router_node`(T11.5)가 LLM으로 메시지 의도를 분류해서 수행한다. 이 정정에 따라 아래 **T15/T16은 폐기**되었다.

---

## 1. T14 — 워크스페이스 페이지 (`/`, `/workspace/{id}`)

### 목표
로그인 사용자가 원고 목록을 보고, 새 원고를 만들고, 특정 원고에서 대화 + 생성 버튼을 사용할 수 있는 3단 레이아웃 SSR 페이지.

### 대상 파일

**1) `app/pages/workspace_pages.py` (신규)**
```python
import os
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.auth_deps import require_user
from app.core.config import settings
from app.core.database import get_database_session
from app.models.manuscript import ConceptType
from app.models.user import User
from app.services.manuscript_service import get_manuscript, list_manuscripts

router = APIRouter()

templates = Jinja2Templates(directory=os.path.join(settings.BASE_DIR, "app", "templates"))


@router.get("/", response_class=HTMLResponse)
async def workspace_root(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscripts = list_manuscripts(db, user)
    return templates.TemplateResponse(
        request,
        "workspace/index.html",
        {
            "manuscripts": manuscripts,
            "concepts": list(ConceptType),
            "active_manuscript": None,
            "messages": [],
        },
    )


@router.get("/workspace/{manuscript_id}", response_class=HTMLResponse)
async def workspace_detail(
    request: Request,
    manuscript_id: uuid.UUID,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscripts = list_manuscripts(db, user)
    active = get_manuscript(db, user, manuscript_id)  # 없으면 NotFoundError(404) 자동 처리
    return templates.TemplateResponse(
        request,
        "workspace/index.html",
        {
            "manuscripts": manuscripts,
            "concepts": list(ConceptType),
            "active_manuscript": active,
            "messages": await _load_messages(request, active),
        },
    )


async def _load_messages(request: Request, manuscript) -> list:
    """체크포인터에서 이전 대화 이력을 복원한다 (ChatMessage 테이블이 없으므로 그래프 상태가 유일한 출처)."""
    svc = request.app.state.chat_service
    config = {"configurable": {"thread_id": str(manuscript.id)}}
    snapshot = await svc.graph.aget_state(config)
    return snapshot.values.get("messages", []) if snapshot and snapshot.values else []
```

- `main.py`에 `workspace_pages_router`를 등록해야 한다: `app.include_router(workspace_pages_router)` 추가, import 라인 추가.
- **주의:** 현재 `app/pages/user_interface.py`가 이미 `/chat`이라는 별개의 구식 채팅 페이지를 갖고 있다(RAG 데모용, `chat.html` 정적 파일 서빙). 이건 Draftsmith와 무관한 기존 기능이므로 **건드리지 않는다.** 새 `workspace_pages.py`가 `/`를 차지하는데, `pages_router`(=`user_interface.py`)가 `/`를 이미 쓰고 있는지 먼저 확인할 것 — 만약 충돌하면 `user_interface.py`의 라우트를 조정해야 하므로 T14 착수 직전에 `grep -n "@router.get(\"/\"" app/pages/user_interface.py`로 재확인.

**2) `ChatService`에 `graph` 속성 노출 확인**
- `app/services/chat_service.py`의 `ChatService.__init__`은 이미 `self.graph = graph`를 저장하므로 `svc.graph.aget_state(...)` 호출에 추가 변경 불필요. `AsyncSqliteSaver` 기반이라 `aget_state`(비동기 버전)를 써야 한다(`get_state`가 아님).

**3) 템플릿 (신규 5개 파일)**

`app/templates/workspace/index.html`:
```html
{% extends "base.html" %}
{% block content %}
<div class="grid grid-cols-[15%_60%_15%] h-screen">
  <aside class="border-r border-[#EBECED] p-4 overflow-y-auto">
    {% include "workspace/_sidebar_left.html" %}
  </aside>
  <main class="flex flex-col h-screen">
    {% include "workspace/_chat_center.html" %}
  </main>
  <aside class="border-l border-[#EBECED] p-4 overflow-y-auto">
    {% include "workspace/_sidebar_right.html" %}
  </aside>
</div>
{% include "workspace/_new_manuscript_modal.html" %}
{% endblock %}
```

`app/templates/workspace/_sidebar_left.html` (원고 목록 + 새 원고 버튼):
```html
<button
  x-data
  @click="$dispatch('open-new-manuscript-modal')"
  class="w-full mb-4 rounded-[8px] bg-[#2383E2] text-white py-2 text-sm font-medium"
>+ 새 원고</button>
<ul class="space-y-1">
  {% for m in manuscripts %}
  <li>
    <a href="/workspace/{{ m.id }}"
       class="block rounded-[6px] px-2 py-1.5 text-sm {% if active_manuscript and active_manuscript.id == m.id %}bg-[#EBECED] font-medium{% else %}hover:bg-[#F6F5F4]{% endif %}">
      {{ m.topic }}
    </a>
  </li>
  {% endfor %}
</ul>
```

`app/templates/workspace/_chat_center.html` (대화창 + 메시지 폼):
```html
<div id="chat-log" class="flex-1 overflow-y-auto p-6 space-y-3">
  {% for m in messages %}
    {% include "workspace/_message.html" with context %}
  {% endfor %}
</div>
{% if active_manuscript %}
<form
  hx-post="/api/chat/{{ active_manuscript.id }}/message"
  hx-target="#chat-log"
  hx-swap="beforeend"
  class="border-t border-[#EBECED] p-4 flex gap-2"
>
  <input name="content" placeholder="메시지 입력…"
         class="flex-1 rounded-[8px] border border-[#c8c4be] px-3 py-2 text-sm" />
  <button type="submit" class="rounded-[8px] bg-[#2383E2] text-white px-4 py-2 text-sm">→</button>
</form>
{% endif %}
```

- **주의:** `_message.html`은 현재 `{{ message.content }}`만 렌더한다(`message.role`이나 구분 클래스 없음). `_chat_center.html`에서 `{% for m in messages %}`로 순회할 때, `messages`는 `BaseMessage` 객체 리스트(`HumanMessage`/`AIMessage`)라서 `_message.html`을 그대로 재사용하면 사용자 메시지와 AI 메시지가 시각적으로 구분되지 않는다. 이건 T14 범위에서 함께 고칠지, 아니면 "일단 AI 메시지 스타일로 통일"하고 넘어갈지 **판단이 필요한 지점** — 작은 범위(role별 클래스 분기)이므로 T14 안에서 `_message.html`에 `{% if message.type == "human" %}`분기를 추가하는 것을 권장.

`app/templates/workspace/_sidebar_right.html` (진행 현황 + 액션 버튼 + 버전 목록):

> **2026-07-02 정정:** 아래 버튼은 `/api/generate/{action}`이 아니라 **채팅과 동일한 엔드포인트**(`/api/chat/{manuscript_id}/message`)를 호출한다. `hx-vals`로 자연어 문구를 `content`에 실어 보내면, 사용자가 직접 그 문구를 타이핑해서 보낸 것과 백엔드 관점에서 완전히 동일하다. 실제 outline/draft/polish 등으로의 분기는 `router_node`의 LLM 분류가 담당하므로, 버튼 문구가 반드시 그 액션으로 분류된다는 보장은 없다(의도가 명확한 문구를 쓰는 것으로 충분히 신뢰 가능한 수준).

```html
{% if active_manuscript %}
<div class="space-y-2 mb-6">
  {% for prompt_text, label in [
      ("이 정도면 괜찮을까요? 점검해주세요.", "점검 요청"),
      ("지금까지 내용에 피드백 부탁드립니다.", "피드백"),
      ("개요부터 잡아주세요.", "개요 생성"),
      ("초고 작성해주세요.", "초고 작성"),
      ("탈고해주세요.", "탈고"),
  ] %}
  <button
    hx-post="/api/chat/{{ active_manuscript.id }}/message"
    hx-vals='{"content": "{{ prompt_text }}"}'
    hx-target="#chat-log" hx-swap="beforeend"
    class="w-full rounded-[8px] border border-[#c8c4be] py-2 text-sm"
  >{{ label }}</button>
  {% endfor %}
</div>
<div id="version-list" class="space-y-1 text-sm">
  <!-- pending_version이 생긴 응답에서 hx-swap-oob="true" #version-list 로 갱신됨 -->
</div>
<button
  hx-post="/api/manuscripts/{{ active_manuscript.id }}/finalize"
  class="w-full mt-4 rounded-[8px] bg-black text-white py-2 text-sm"
>최종 확정</button>
{% else %}
<p class="text-sm text-[#787671]">원고를 선택하거나 새로 만드세요.</p>
{% endif %}
```

- **미해결 후속 작업(T14 착수 시 처리):** `/api/generate/*`가 사라졌으므로, `pending_version`이 생겼을 때 우측 `#version-list`를 OOB로 갱신하는 책임이 이제 `chat_pages.py::send_message` 응답 쪽으로 옮겨온다. 현재 `_message.html`은 AI 메시지만 렌더하므로, `chat_pages.py`가 `state.get("pending_version")`을 확인해서 OOB 블록을 함께 반환하도록 T14에서 수정해야 한다(T15의 `_generate_result.html` OOB 패턴을 `chat_pages.py` 쪽으로 이식).

`app/templates/workspace/_new_manuscript_modal.html` (Alpine 모달, `teaching` 선택 시 `audience_level` 입력 노출):
```html
<div x-data="{ open: false }" @open-new-manuscript-modal.window="open = true">
  <div x-show="open" class="fixed inset-0 bg-black/30 flex items-center justify-center" style="display:none">
    <form hx-post="/api/manuscripts" hx-ext="json-enc" class="bg-white rounded-[12px] p-6 w-[400px] space-y-3">
      <input name="topic" placeholder="주제" required class="w-full border border-[#c8c4be] rounded-[8px] px-3 py-2 text-sm" />
      <select name="concept" x-data x-model="concept" required class="w-full border border-[#c8c4be] rounded-[8px] px-3 py-2 text-sm">
        {% for c in concepts %}<option value="{{ c.value }}">{{ c.value }}</option>{% endfor %}
      </select>
      <input x-show="concept === 'teaching'" name="audience_level" placeholder="독자 수준 (예: 초급)"
             class="w-full border border-[#c8c4be] rounded-[8px] px-3 py-2 text-sm" style="display:none" />
      <button type="submit" class="w-full bg-[#2383E2] text-white rounded-[8px] py-2 text-sm">만들기</button>
    </form>
  </div>
</div>
```

- **의존성 주의:** `hx-ext="json-enc"`는 HTMX 확장 스크립트가 별도로 필요하다(`https://unpkg.com/htmx.org@1.9.12/dist/ext/json-enc.js`). `base.html`에 이 스크립트 태그를 추가해야 하며, 원본 `POST /api/manuscripts`는 `ManuscriptCreateRequest`(JSON body, `manuscripts.py:19`)를 받으므로 HTMX 기본 폼 인코딩(form-urlencoded)으로는 동작하지 않는다. **대안**: json-enc 확장을 추가하거나, `manuscripts.py`의 `create` 엔드포인트가 `Form(...)` 파라미터도 받도록 바꾸는 것. 후자는 기존 API 계약(JSON)을 깨므로, **json-enc 확장 추가 쪽을 권장.**
- 새 원고 생성 성공 후 `/workspace/{id}`로 리다이렉트해야 하는데, 현재 `manuscripts.py::create`는 JSON만 반환한다. HTMX 리다이렉트를 위해 응답 헤더 `HX-Redirect: /workspace/{id}`가 필요 — 이건 `app/api/endpoints/manuscripts.py`의 `create` 함수에 `response: Response` 파라미터를 추가하고 `response.headers["HX-Redirect"] = f"/workspace/{manuscript.id}"`를 설정하는 작은 수정이 필요하다(T14 범위에 포함).

### 검증
```bash
uv run pytest -q
uv run ruff check app/pages app/templates 2>&1 | tail -20
```
- 신규 `tests/test_workspace_pages.py` 추가 권장:
  - 미인증 시 `/`, `/workspace/{id}` → 401(또는 로그인 페이지 리다이렉트, 현재 `require_user`는 401을 던지므로 401 확인).
  - 인증 후 `/` → 200, 본문에 "새 원고" 버튼 텍스트 포함.
  - 존재하지 않는 `manuscript_id`로 `/workspace/{id}` → 404(`NotFoundError` 자동 변환).

---

## 2. T15 — Generate API: `/api/generate/draft` (❌ 폐기됨, 2026-07-02)

> **이 태스크는 더 이상 구현하지 않는다.** 원본 설계는 "초고 작성" 버튼이 `/api/generate/draft`라는 전용 엔드포인트를 호출하는 것을 전제로 했으나, 사용자가 이를 정정함: 버튼은 자연어 문구를 채팅과 동일한 단일 채널(`/api/chat/{manuscript_id}/message`)로 전송하는 UX 장치일 뿐이고, 실제 draft 분기는 T11.5의 `router_node` LLM 분류가 담당한다. 아래 원본 내용은 **정정 이전 설계 기록**으로만 남겨둔다(참고용, 구현 금지).

<details>
<summary>원본 설계 (참고용, 구현하지 않음)</summary>

### 목표
"초고 작성" 버튼 클릭 시 `ChatService.run(action="draft")`를 호출하고, 결과를 대화창(AI 메시지) + 우측 버전 목록(OOB swap) 두 군데에 반영.

### 대상 파일

**`app/pages/generate_pages.py` (신규)** — HTML을 반환하므로 `app/pages/`에 위치(엔드포인트 파일 아님, CLAUDE.md 규칙 준수).

```python
import os
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from langchain_core.messages import AIMessage
from sqlalchemy.orm import Session

from app.core.auth_deps import require_user
from app.core.config import settings
from app.core.database import get_database_session
from app.models.user import User
from app.pages.chat_pages import get_chat_service
from app.services.chat_service import ChatService
from app.services.manuscript_service import get_manuscript

router = APIRouter(prefix="/api/generate", tags=["generate"])

templates = Jinja2Templates(directory=os.path.join(settings.BASE_DIR, "app", "templates"))


@router.post("/draft")
async def generate_draft(
    request: Request,
    manuscript_id: uuid.UUID,
    user: User = Depends(require_user),
    svc: ChatService = Depends(get_chat_service),
    db: Session = Depends(get_database_session),
):
    manuscript = get_manuscript(db, user, manuscript_id)
    state = await svc.run(manuscript, user_action="draft")
    last_ai = next(
        msg for msg in reversed(state["messages"]) if isinstance(msg, AIMessage)
    )
    pending_version = state.get("pending_version")
    return templates.TemplateResponse(
        request,
        "workspace/_generate_result.html",
        {"message": last_ai, "pending_version": pending_version},
    )
```

- `svc.run()`은 `user_message=None`으로 호출된다(대화 없이 액션만 트리거) — `ChatService.run()`의 `input_state["messages"]`는 `user_message`가 없으면 `[]`이므로, 노드는 **이전 체크포인트의 대화 이력 위에서** 초고를 생성한다(정상 동작).
- **`pending_version`이 `None`일 가능성**: `draft_node`는 항상 `pending_version`을 채우므로(코드 확인됨, `draft.py`) draft 액션에서는 걱정 없음. 다만 방어적으로 템플릿에서 `{% if pending_version %}`로 감싼다.

**`app/templates/workspace/_generate_result.html` (신규)** — 대화창에 AI 메시지 추가 + OOB로 버전 목록 갱신:
```html
{% include "workspace/_message.html" %}
{% if pending_version %}
<div id="version-list" hx-swap-oob="beforeend">
  <div class="flex justify-between text-xs text-[#787671] py-1">
    <span>{{ pending_version.kind }}</span>
    <span>v{{ pending_version.get("version_id", "")[:8] }}</span>
  </div>
</div>
{% endif %}
```
- HTMX `hx-swap-oob="beforeend"`를 쓰려면 `id="version-list"`를 가진 요소가 **응답 안에도** 있어야 하고, `_sidebar_right.html`의 `#version-list`와 짝이 맞아야 한다(HTMX OOB 규칙).

### 검증
```bash
uv run pytest tests/test_generate_api.py -q
uv run ruff check app/pages/generate_pages.py
```
- 신규 `tests/test_generate_api.py`: `chat_service_override` fixture(=`tests/test_chat_api.py`에 이미 있는 패턴, `MagicMock()` storage 사용) 재사용. `fake_llm`이 고정 응답("테스트 응답입니다.")을 주므로:
  - `POST /api/generate/draft?manuscript_id=...` → 200, 응답 본문에 "테스트 응답입니다" 포함.
  - `storage.save`가 1회 호출됐는지 (`MagicMock` assert).
  - 미인증 401, 타인 원고 404.

---

</details>

---

## 3. T16 — inspect / feedback / outline / polish 라우트 (❌ 폐기됨, 2026-07-02)

> **이 태스크도 T15와 동일한 이유로 더 이상 구현하지 않는다.** `inspect`/`feedback`/`outline`/`polish` 전부 채팅 메시지 하나로 들어오고 `router_node`가 분류한다. 아래 원본 내용은 참고용으로만 남겨둔다.

<details>
<summary>원본 설계 (참고용, 구현하지 않음)</summary>

### 목표
T15와 동일한 패턴을 4개 액션에 반복. `svc.run(m, user_action=<action>)` 하나면 라우팅은 LangGraph가 알아서 처리하므로 **라우트 코드 자체는 T15 복붙 + 액션명 치환** 수준.

### 대상 파일
`app/pages/generate_pages.py`에 4개 함수 **추가** (같은 파일, 새 파일 아님):

```python
@router.post("/inspect")
async def generate_inspect(
    request: Request,
    manuscript_id: uuid.UUID,
    user: User = Depends(require_user),
    svc: ChatService = Depends(get_chat_service),
    db: Session = Depends(get_database_session),
):
    manuscript = get_manuscript(db, user, manuscript_id)
    state = await svc.run(manuscript, user_action="inspect")
    last_ai = next(msg for msg in reversed(state["messages"]) if isinstance(msg, AIMessage))
    return templates.TemplateResponse(
        request, "workspace/_generate_result.html",
        {"message": last_ai, "pending_version": state.get("pending_version")},
    )


@router.post("/feedback")
async def generate_feedback(...):  # inspect와 완전히 동일한 본문, user_action="feedback"만 다름
    ...


@router.post("/outline")
async def generate_outline(...):  # user_action="outline"
    ...


@router.post("/polish")
async def generate_polish(
    request: Request,
    manuscript_id: uuid.UUID,
    base_version_id: str | None = None,  # 원본 계획 3.4절: polish는 base_version_id 파라미터를 받음
    user: User = Depends(require_user),
    svc: ChatService = Depends(get_chat_service),
    db: Session = Depends(get_database_session),
):
    manuscript = get_manuscript(db, user, manuscript_id)
    state = await svc.run(manuscript, user_action="polish")
    ...
```

- **중요한 미해결 이슈 (구현 전 확인 필요):** `polish_node`(`app/graph/nodes/polish.py`)를 확인한 결과 `outline_node`/`draft_node`와 동일하게 `state["messages"]`(대화 이력 전체)만 참고하고, **`base_version_id`로 특정 초고 버전의 파일 내용을 명시적으로 불러오는 로직이 없다.** 즉 지금 그래프 설계상 "탈고"는 "지금까지의 대화 맥락에서 다시 한 번 생성"이지, "특정 draft 파일을 대상으로 다듬기"가 아니다. 이 갭은 T16에서 다음 중 하나로 해결해야 한다:
  1. **(권장, 최소 변경)** `base_version_id`를 받되 지금은 실제로 사용하지 않고 무시 — 원고 대화 이력에 이미 초고 내용이 `AIMessage`로 남아있으므로 LLM이 문맥상 최근 초고를 참고해 탈고할 수 있음. 라우트 시그니처만 원본 계획과 맞추고 TODO 주석 없이 그대로 둔다(현재 학습용 주석 정책과 무관하므로 주석 추가 금지, 대신 이 계획 문서에 기록).
  2. (확장, 범위 밖) `base_version_id`로 `ManuscriptVersion.storage_key`를 조회해 파일 내용을 `input_state["messages"]`에 `HumanMessage`로 주입 — 이건 `chat_service.py::run()` 시그니처 변경이 필요해 T16 범위를 넘어선다. **지금은 하지 않는다.**
- `inspect`/`feedback`은 `pending_version`을 만들지 않으므로(그래프 확인됨, `converse_node`/`feedback_node`) `_generate_result.html`의 `{% if pending_version %}` 분기 덕분에 버전 목록 OOB 갱신이 자동으로 생략된다 — 별도 분기 코드 불필요.

### 검증
```bash
uv run pytest tests/test_generate_api.py -q
uv run ruff check app/pages/generate_pages.py
```
- `test_generate_api.py`에 4개 액션 테스트 추가: 각 액션 호출 시 200 + AI 응답 텍스트 포함. `outline`/`polish`는 `pending_version` 존재까지 확인, `inspect`/`feedback`은 버전 목록 OOB 블록이 응답에 **없어야** 함을 확인(`"version-list" not in response.text`).

---

</details>

---

## 4. T17 — finalize 라우트

### 목표
`POST /api/manuscripts/{id}/finalize?version_id=...` — 해당 `ManuscriptVersion.is_finalized=True`, `Manuscript.status=FINALIZED`.

### 설계 결정: JSON API로 유지 (HTML partial 아님)
"최종 확정"은 결과가 복잡한 partial을 필요로 하지 않고(성공/실패만 표시), 원본 계획 3.2절도 `Response 200`(JSON)으로 명시했다. 따라서 T15/T16과 달리 **`app/api/endpoints/manuscripts.py`에 추가**한다(HTML을 반환하지 않으므로 CLAUDE.md의 pages/ 강제 규칙 대상이 아님).

### 대상 파일

**1) `app/repositories/manuscript_repo.py`에 함수 추가:**
```python
def get_version_owned(db: Session, user: User, manuscript_id: uuid.UUID, version_id: uuid.UUID) -> ManuscriptVersion | None:
    return (
        db.query(ManuscriptVersion)
        .join(Manuscript, Manuscript.id == ManuscriptVersion.manuscript_id)
        .filter(
            ManuscriptVersion.id == version_id,
            ManuscriptVersion.manuscript_id == manuscript_id,
            Manuscript.user_id == user.id,
        )
        .first()
    )


def finalize(db: Session, manuscript: Manuscript, version: ManuscriptVersion) -> None:
    version.is_finalized = True
    manuscript.status = ManuscriptStatus.FINALIZED
    db.add(version)
    db.add(manuscript)
    db.commit()
```
(`ManuscriptVersion`, `ManuscriptStatus` import 추가 필요.)

**2) `app/services/manuscript_service.py`에 함수 추가:**
```python
def finalize_manuscript(db: Session, user: User, manuscript_id: uuid.UUID, version_id: uuid.UUID) -> Manuscript:
    manuscript = get_manuscript(db, user, manuscript_id)  # NotFoundError 자동 처리
    version = manuscript_repo.get_version_owned(db, user, manuscript_id, version_id)
    if not version:
        raise NotFoundError("버전을 찾을 수 없습니다.")
    manuscript_repo.finalize(db, manuscript, version)
    logger.info("manuscript finalized: manuscript_id=%s version_id=%s", manuscript_id, version_id)
    return manuscript
```

**3) `app/api/endpoints/manuscripts.py`에 라우트 추가:**
```python
@router.post("/{manuscript_id}/finalize", response_model=ManuscriptResponse)
def finalize(
    manuscript_id: uuid.UUID,
    version_id: uuid.UUID,
    user: User = Depends(require_user),
    db: Session = Depends(get_database_session),
):
    manuscript = finalize_manuscript(db, user, manuscript_id, version_id)
    return ManuscriptResponse(
        id=str(manuscript.id),
        topic=manuscript.topic,
        concept=manuscript.concept,
        status=manuscript.status,
        audience_level=manuscript.audience_level,
    )
```
- `version_id`를 쿼리 파라미터로 받는다(원본 계획과 동일, `Body`가 아님 — FastAPI는 `UUID` 타입의 비-Pydantic-model 파라미터를 자동으로 쿼리 파라미터로 취급).

### 검증
```bash
uv run pytest tests/test_manuscript.py -q
uv run ruff check app/api/endpoints/manuscripts.py app/services/manuscript_service.py app/repositories/manuscript_repo.py
```
- `tests/test_manuscript.py`에 시나리오 추가: draft 생성(~~T15 라우트~~ **폐기됨** → 채팅으로 "초고 작성해주세요" 전송하거나 직접 `ManuscriptVersion` 삽입) → finalize 호출 → `status == "finalized"`, `version.is_finalized is True`. 존재하지 않는 `version_id` → 404. 타인 원고의 버전 → 404(소유권 검증).

---

## 5. T18 — E2E 흐름 테스트

### 목표
회원가입부터 초고 생성까지 전체 플로우를 하나의 테스트 파일로 검증. 원본 계획 6개 시나리오 중 **5번(한자 제거)** 은 세션 중 `chinese_filter`로 개명됐으므로 검증 문구도 한자 그대로(`"漢字"`) 유지하면 된다(정규식은 한자 유니코드 대역이라 이름과 무관).

> **2026-07-02 정정 반영:** `/api/generate/draft` 호출이 사라졌으므로, "초고 생성" 시나리오는 이제 채팅 메시지("초고 작성해주세요")를 보내는 것으로 검증한다. 그래프 1회 호출(`graph.ainvoke`)마다 `router_node`(분류)와 phase 노드(생성) 두 번의 LLM 호출이 발생하므로, `fake_llm` 픽스처(고정 응답 1개, 매 호출 동일 텍스트 반환)로는 `router_node`가 항상 `"say"`로 폴백해 draft 분기를 태울 수 없다. draft 시나리오 전용으로 `FakeListChatModel(responses=["draft", "초고 본문입니다."])`를 이 테스트 안에서 직접 등록해서 써야 한다(1번째 호출=분류→"draft", 2번째 호출=`draft_node`의 생성 결과).

### 대상 파일: `tests/test_chat_flow.py` (신규)

```python
import pytest
from unittest.mock import MagicMock

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.graph import llm_registry
from app.pages.chat_pages import get_chat_service
from app.graph.builder import build_graph
from app.graph.checkpointer import make_checkpointer
from app.services.chat_service import ChatService
from main import app as fastapi_app


@pytest.fixture
async def e2e_chat_service(fake_llm, db_session):
    storage = MagicMock()
    async with make_checkpointer(":memory:") as checkpointer:
        graph = build_graph(checkpointer)
        svc = ChatService(graph=graph, storage=storage, db_factory=lambda: db_session)
        fastapi_app.dependency_overrides[get_chat_service] = lambda: svc
        yield svc, storage
        fastapi_app.dependency_overrides.pop(get_chat_service, None)


def test_full_manuscript_flow(client, e2e_chat_service):
    svc, storage = e2e_chat_service

    # 1) 가입/로그인 (auth.py의 signup이 즉시 쿠키를 발급하므로 별도 로그인 호출 불필요)
    signup_res = client.post(
        "/api/auth/signup",
        json={"login_id": "e2euser", "password": "password123", "nickname": "E2E"},
    )
    assert signup_res.status_code == 201

    # 2) 원고 생성
    create_res = client.post(
        "/api/manuscripts", json={"topic": "RSC 회고", "concept": "tech_deepdive"}
    )
    assert create_res.status_code == 201
    manuscript_id = create_res.json()["id"]

    # 3) 메시지 3회 전송 → 체크포인트 누적 확인
    # fake_llm(고정 응답)이 router 분류 호출에도 그대로 쓰이므로 매번 "say"로 폴백 → converse 노드로 라우팅(정상)
    for i in range(3):
        r = client.post(f"/api/chat/{manuscript_id}/message", data={"content": f"메시지 {i}"})
        assert r.status_code == 200

    import asyncio
    config = {"configurable": {"thread_id": manuscript_id}}
    snapshot = asyncio.get_event_loop().run_until_complete(svc.graph.aget_state(config))
    # HumanMessage 3 + AIMessage 3 = 6개 (fake_llm 고정 응답이므로 매번 동일 텍스트)
    assert len(snapshot.values["messages"]) == 6

    # 4) 초고 작성 요청 → 파일 저장 + DB row 확인
    # router 분류(1번째 LLM 호출) + draft_node 생성(2번째 호출)이 순서대로 소비되도록 전용 FakeListChatModel 등록
    original_llm = llm_registry._registry.get("default")
    llm_registry.register("default", FakeListChatModel(responses=["draft", "초고 본문입니다."]))
    try:
        draft_res = client.post(
            f"/api/chat/{manuscript_id}/message", data={"content": "초고 작성해주세요"}
        )
        assert draft_res.status_code == 200
    finally:
        if original_llm is not None:
            llm_registry.register("default", original_llm)
    storage.save.assert_called_once()

    # 5) 다른 원고의 thread_id 격리 확인
    create_res2 = client.post(
        "/api/manuscripts", json={"topic": "다른 글", "concept": "til"}
    )
    manuscript_id2 = create_res2.json()["id"]
    config2 = {"configurable": {"thread_id": manuscript_id2}}
    snapshot2 = asyncio.get_event_loop().run_until_complete(svc.graph.aget_state(config2))
    assert not snapshot2.values or not snapshot2.values.get("messages")
```

- **한자 제거 시나리오(원본 5번)는 별도 유닛 테스트로 이미 커버됨** (`tests/test_graph_nodes.py::test_chinese_prevent_node_removes_chinese_from_message_and_pending_version`, `tests/test_chinese_filter.py`) — E2E에서 중복 검증할 필요 없다.
- `asyncio.get_event_loop().run_until_complete(...)`는 pytest-asyncio 환경에서 이벤트 루프 충돌 가능성이 있다 — 실제 작성 시 `test_full_manuscript_flow`를 `@pytest.mark.asyncio async def`로 바꾸고 `await svc.graph.aget_state(...)`를 직접 쓰는 편이 안전하다(TestClient는 동기 호출이라 async 테스트 안에서 `client.post`를 그대로 써도 무방 — `httpx.TestClient`는 내부적으로 동기 래퍼).

### 검증
```bash
uv run pytest tests/test_chat_flow.py -v
uv run pytest -q   # 전체 회귀
```

---

## 6. T19 — Ruff / 타입 정리

### 목표
T14~T18에서 새로 생긴 파일들을 포함해 전체 lint 클린.

### 절차
```bash
uv run ruff check --fix app tests
uv run ruff check app tests   # --fix 후 잔여 경고 수동 확인
```
- 세션 중 확인된 **기존에 존재하던(이번 작업과 무관한) 경고 3건**은 손대지 않는다(CLAUDE.md "surgical changes" 원칙 — 언급만 하고 삭제하지 않음):
  - `app/core/vectorstore.py` — 미사용 import
  - `tests/test_rag_quality.py` — f-string 관련 경고
  - `tests/test_upload.py` — 미사용 변수
- pyright/mypy 관련해서는 세션 중 논의된 대로 프로젝트에 타입 체커 설정이 없으므로(=CI 게이트 아님) T19에서 별도 조치 불필요. 다만 `app/graph/builder.py`의 `add_node` 호출부에서 계속 신경 쓰인다면, 이 시점에 한 번 `dict` → `dict[str, Any]` 반환 타입 좁히기를 노드 파일 전체에 일괄 적용하는 것도 고려 가능(선택 사항, 필수 아님).

### 검증
```bash
uv run pytest -q
uv run ruff check app tests
```

---

## 7. T20 — 로컬 수동 실행 확인 안내

### 목표
사용자가 브라우저로 직접 회원가입 → 로그인 → 새 원고 → 대화 → 초고 흐름을 확인할 수 있도록 안내 문서/예시 파일 준비. **코드 작업이 아니라 안내 산출물이 목표**이므로 다른 태스크와 성격이 다르다.

### 대상 파일

**1) `.env.example` (신규, 레포 루트)**
```
DEEPSEEK_API_KEY=
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
JWT_SECRET=change-me-in-production
```
- 실제 `Settings` 필드명과 정확히 맞춰야 한다 — `app/core/config.py`를 다시 열어 필드명 오탈자 없는지 확인 후 작성(현재 확인된 것: `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`, `DEEPSEEK_MODEL`, `STORAGE_ROOT`는 기본값이 있어 필수 아님 — `JWT_SECRET`/`DATABASE_URL` 등 나머지 필드는 T20 착수 시 `config.py` 전체를 재확인해서 필수 항목만 `.env.example`에 포함).

**2) 실행 확인 절차 (사용자에게 안내할 내용, 문서화는 하되 별도 README 파일을 새로 만들 필요는 없음 — 이 계획 문서 자체가 기록 역할):**
```bash
uv run uvicorn app.main:app --reload
```
- 브라우저에서: `/signup` → 가입 → `/` 리다이렉트(또는 T14에서 만든 워크스페이스 루트) → "새 원고" → 주제/컨셉 입력 → `/workspace/{id}` 이동 확인 → 메시지 입력 → AI 응답 확인 → "초고 작성" 버튼 → 우측 버전 목록 갱신 확인 → "최종 확정" 버튼 → 상태 변경 확인.
- **DeepSeek API 키가 실제로 유효해야** LLM 호출이 성공한다 — 로컬 수동 확인 시 `fake_llm`이 아니므로 `.env`에 진짜 키가 필요하다는 점을 사용자에게 명확히 안내해야 함(이 점이 T20의 핵심 산출물).

### 검증
- 자동화된 pytest 대상이 아니다. 사용자가 직접 브라우저로 확인하는 단계이므로, Claude가 "완료"로 표시하려면 **실행 방법과 확인 체크리스트를 사용자에게 제시하는 것으로 충분**하고, 실제 브라우저 조작은 사용자 몫이다.

---

## 8. 전체 실행 순서 및 의존성

> **2026-07-02 정정 반영:** T15/T16이 폐기되면서 의존 관계가 단순해졌다.

```
T11.5 (router_node LLM 의도 분류) — ✅ 완료 (2026-07-02)

T14 (워크스페이스 페이지)
  └─ 전제: T11.5 완료 (우측 버튼이 채팅 엔드포인트로 자연어를 보내므로 분류기가 먼저 있어야 의미가 있음)
  └─ 그 외 전제 없음 (기존 T6/T8/T13 결과물 사용)

T17 (finalize)
  └─ 전제: 없음 (독립적인 파일들: manuscripts.py, manuscript_service.py, manuscript_repo.py)
  └─ T14와 병렬 진행 가능

T18 (E2E 테스트)
  └─ 전제: T14, T17 완료 (모든 화면 흐름이 실제로 존재해야 흐름 테스트 가능)

T19 (Ruff/타입 정리)
  └─ 전제: T14, T17, T18 전부 완료

T20 (로컬 실행 안내)
  └─ 전제: T14, T17, T18, T19 전부 완료
```

**권장 진행 순서:** T14 → T17(병렬 가능) → T18 → T19 → T20.

---

## 9. 이 문서에서 새로 발견/결정된 이슈 목록 (요약)

1. `ChatMessage` SQL 테이블 미구현 — 대화 이력 복원은 `graph.aget_state()`로 처리 (T14).
2. ~~`/api/generate/*`, `finalize`는 반환 타입에 따라 배치가 갈린다~~ **정정(2026-07-02):** `/api/generate/*`는 폐기됨. `finalize`만 JSON → `app/api/endpoints/`에 남는다 (T17).
3. `POST /api/manuscripts`가 JSON body를 받으므로, HTMX 새 원고 모달은 `json-enc` 확장이 필요하고 `base.html`에 스크립트 태그 추가가 필요 (T14).
4. 새 원고 생성 성공 시 `HX-Redirect` 헤더를 위해 `manuscripts.py::create`에 `response: Response` 파라미터 추가 필요 (T14, 기존 엔드포인트에 대한 최소 수정).
5. ~~`polish` 액션의 `base_version_id`는...~~ **정정(2026-07-02):** `base_version_id` 파라미터를 받는 별도 라우트 자체가 없어졌으므로 이 이슈는 해소됨. "특정 버전을 대상으로 탈고"가 필요해지면, 채팅 메시지에 대상 버전을 자연어로 언급하게 하거나 향후 별도 설계가 필요(범위 밖, 미해결로 남김).
6. `_message.html`이 사용자/AI 메시지를 구분하지 않는 문제 — T14에서 `message.type` 분기 추가 권장.
7. T19에서 굳이 손 안 대도 되는 기존 ruff 경고 3건 목록화(재확인 방지).
8. **(신규, 2026-07-02)** `router_node`가 매 메시지마다 LLM을 1회 추가 호출하게 되어, 채팅 1턴당 LLM 호출 횟수가 항상 2회(분류 + 생성)로 늘어났다. 지연시간/비용에 영향이 있을 수 있음 — 필요시 향후 저비용 모델로 분류만 분리하는 최적화를 고려할 수 있으나 지금은 범위 밖.
9. **(신규, 2026-07-02)** `pending_version`이 생겼을 때 우측 `#version-list`를 OOB로 갱신하는 책임이 `/api/generate/*`에서 `chat_pages.py::send_message`로 이전됨 — T14 착수 시 반드시 반영(1절 T14 섹션의 미해결 후속 작업 참조).

**끝.**
