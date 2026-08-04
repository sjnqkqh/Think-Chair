# Agentic RAG 채팅 E2E 최소 구조 — 세션 핸드오프

- 작성일: 2026-08-04
- PR: [#24](https://github.com/sjnqkqh/Think-Chair/pull/24) **머지됨**
- 설계: `docs/specs/2026-08-03-agentic-rag-vertical-mvp-design.md`
- 구현 계획: `docs/plans/agentic-research-rag/09-agentic-rag-vertical-mvp.md`
- 목적: **새 세션이 같은 텐션으로** 이어갈 수 있게, 끝난 일·남은 일·하지 말 일을 한곳에 둔다.

> **이름 정리:** 문서에 쓰인 “세로 MVP” = **채팅에서 조사 한 바퀴를 끝까지 돌릴 수 있는 최소 E2E 구조**.  
> (문서 PR 00~06을 각각 풀로 끝낸 상태가 아니라, 가로 슬라이스를 건너뛰고 한 사이클만 연결한 것.)

## 0. 작업 텐션 (새 세션이 먼저 읽을 것)

대화·구현에서 이미 합의된 태도. 문서·코드와 어긋나면 **이 섹션과 사용자 확인을 우선**한다.

1. **제품 ≠ 평가**  
   - 제품: 조사 job = 웹 수집·인덱싱·job 상태. 채팅 = **매 턴 Chroma 검색**으로 근거를 프롬프트에 넣음. Route 뒤에는 자료가 있으면 **그걸로 실제로 답**해야 함 (silent/shadow 로그가 아님).  
   - 평가(job 끝): baseline / grounded / pairwise는 **관측용**. **승률 게이트로 배포/PR을 막지 않음** (계약에서 폐기).  
   - 정량 문제집: `11-rag-judge-corpus-plan.md` — **필요**, 게이트 아님.  
     **의도(2026-08-04 확정):** 고정 일반론만(phase=`say`|`feedback` 구분) → `load_evidence_text_for_turn` + **해당 노드 직접** → Judge **절대 점수** → 마크다운. 평가 중 job·Route 없음. **LangFeather 트레이싱**.  
     질문 = **「서비스 전반이 성장하는가」**. pairwise “근거 붙이면…”은 이 문제집 질문이 **아님**.
2. **consume 금지**  
   - `prepared_evidence_json` / `consumed_at` 제품 handoff는 **제거된 설계**. 다시 넣지 말 것.
3. **컨셉 게이트**  
   - 웹 조사 트리거·job 생성은 **딥다이브·수업 자료만**. TIL/에세이/회고는 감지해도 `research_required` 없음.
4. **트리거 의도**  
   - “확인해 주세요” 요청이 아님. **일반론·모범 사례·대략 수치 주장**을 더 좋은 근거로 보강하기 위함.  
   - live E2E 실패는 종종 **트리거/검색 품질 신호**이지, 무조건 제품 버그가 아님.
5. **모델**  
   - 생성·판정: **DeepSeek**. 임베딩: **OpenAI**.  
6. **공용 인덱싱**  
   - 웹 수집분을 public으로 넣는 것은 **버그가 아니라 제품 의도**(프로젝트/서비스가 쓸수록 근거가 쌓임).  
   - `admit_source=... "public"` stub를 “나중에 private 정책으로 고칠 TODO”로 두지 말 것.
7. **취소 API**  
   - 제품 UX에 취소 버튼이 없어도 **cancel API·상태 처리는 유지** (사전 결정/문서에서 온 계약).
8. **ORM에 팩토리 몰아넣기 금지**  
   - Source/Job/Url 생성 헬퍼를 모델에 잔뜩 넣는 방향은 **revert됨** (`845644f`).  
   - 예외로 남긴 것: `ResponseComparisonRecord.from_job_evaluation` 정도.
9. **런타임 ALTER 금지**  
   - 스키마는 ORM + 별도 마이그레이션. 앱 기동 시 `ALTER TABLE` 보정 코드 넣지 않음.
10. **에이전트 문서**  
    - `.agents/AGENTS.md` / `CLAUDE.md` 본문은 **영어**. 사용자와의 채팅·**커밋 메시지 설명은 한국어** (`feat:` 등 prefix는 가능).
11. **PR 범위**  
    - #24는 채팅 E2E 최소 구조를 한 브랜치에 몰아넣은 **과도한 PR**이었고 머지됨. 후속은 작게.
12. **최소 변경**  
    - 요청 밖 추측 기능·추상화·주변 정리 금지. 이름·용어는 도메인 말로, 세션 로컬 은어를 공유 어휘처럼 쓰지 말 것.

## 1. MVP 완료 기준 vs 현재

설계 §7 기준.

| # | 완료 기준 | 상태 | 근거 / 메모 |
|---|---|---|---|
| 1 | 조사 필요 턴에서 `research_required` + job 생성 | **됨** | `evidence_need` + eligibility + chat SSE + `research_job_service` |
| 2 | job이 웹 조사 포함 근거 준비 또는 실패/부족 상태 | **됨** | `research_job_runner` / `stages` / `web_research` |
| 3 | job 후 baseline·grounded·비교 DB 저장 | **됨** | 평가 best-effort, DeepSeek, `judgment_json` (0~100 점수) |
| 4 | UI는 `근거 준비됨`만, 답 자동 수정·자동 후속 없음 | **됨** | `_chat_center.html` 폴링 |
| 5 | 이후 턴 인덱스 검색으로 근거 사용 (소비 없음) | **됨** | `turn_evidence` ← `chat_service.begin_turn` |
| 6 | private cross-user 0, EvidenceContext 밖 citation 0 | **대체로** | citation ID/URL 가드·tenant 필터 테스트 있음. 공용 웹 인덱싱은 의도 |
| 7 | 비조사 채팅·문서 생성 회귀 없음 | **대체로** | FakeList 경로 embeddings 스텁으로 e2e flake 완화. 공유 Session/FakeList 레이스는 **잔존 위험** |
| 8 | 승률 숫자 게이트 없음 | **됨** | 의도적 제외 |

구현 계획 `09` 작업 0~7도 코드상 연결되어 있다. 예전 계획서 전체(문제집·점수선·채점)까지 끝낸 건 아님 — §2.5.

## 2. 진행된 작업 (테마별)

### 제품 경로

- 컨셉 게이트: `app/research/research_eligibility.py`
- 주장 감지: `app/research/evidence_need.py` (일반론·수치 등)
- 채팅: `research_required` SSE, 딥다이브/수업만 조사 + **매 턴** `load_evidence_text_for_turn`
- job API: 생성·조회·취소, 엔드포인트 얇고 실행 배선은 `research_job_service`
- 오케스트레이션: `research_job_context` / `stages` / `runner` — 수집으로 제품 완료 결정 후 평가
- 사용량: 원고당 job **최대 5회** (`ResearchUsage`)
- UI: 폴링, completed/partial 시 근거 준비됨

### 평가 경로

- baseline / grounded / pairwise → `ResponseComparisonRecord`
- 점수: 기준별 0~100 → winner 유도, `judgment_json`에 저장
- 생성·판정 모델: DeepSeek (임베딩은 OpenAI 유지)

### 테스트·하네스

- 단위: `tests/unit/research/`, chat/eligibility/usage/runner/stages 등
- live E2E: `tests/e2e/test_live_research_conversation.py` (기본 skip, 실 Brave/OpenAI, tmp DB·Chroma)
- FakeList 공용 픽스처: `chat_app_state`가 `load_evidence_text_for_turn`을 스텁 → **실 embeddings 차단** (`0327f10`)

### 문서·규칙

- 설계/계획 갱신 (매 턴 검색, 평가 분리)
- 에이전트 규칙: thin endpoints, no runtime ALTER, 공유 어휘, **한글 커밋 메시지**

### 명시적 롤백 (다시 넣지 말 것)

- Research Source/Job ORM 팩토리 잔뜩 넣기 → `845644f`로 revert

## 2.5 예전 계획서(PR 00~06) 기준으로 보면

예전 문서는 층층이 나누고 숫자 합격선까지 두자는 **긴 로드맵**이었다.
지금 머지된 것은 **채팅에서 조사 한 바퀴**만 이은 최소 E2E다.

| 번호 | 쉬운 말 | 지금 (2026-08-04 결정 반영) |
|---|---|---|
| 00 | Judge용 **문제집** | **필요함.** 게이트 아님. **서비스 성장 관측**(절대 점수·시계열·제품 노드). → `11-rag-judge-corpus-plan.md` |
| 01~02 | 검색·수집·인덱스 | **됨** |
| 03 | 근거 검색·답·(옛)합격선 | 검색·답·비교 저장 **됨**. **합격선은 계약에서 폐기** |
| 04 | 조사필요 채점·silent 로그 | **쓰지 않음.** 원하는 것은 Route 뒤 **실제 RAG 답** |
| 05 | job 실행 + 재시작 때 죽은 job 표시 | 실행 **됨**. 재시작 정리 **없음** (필수로 보지 않음) |
| 06 | 채팅 연결 | **됨** (매 턴 검색 주입). Route 후 RAG 체감은 계속 다듬을 여지 |

## 3. 남은 작업 / 열린 문제

### P0 — 다음으로 의미 있는 일

- [ ] **Judge 정량 문제집** 확정·수집·실행기(절대 점수 MD) → `11-rag-judge-corpus-plan.md`
- [ ] **Route 이후 RAG가 답에 실제로 실리게** — 인덱스에 있거나 조사로 모인 근거로 대화 응답 (silent 로그 아님)
- [ ] 수동 스모크: 일반론 → job → 근거 준비됨 → 다음 턴 답 체감

### P1 — 테스트 빚

- [ ] `chat_app_state` Session 공유 / FakeList·문서생성 대기 레이스

### P2 — 있으면 편함 (제품 핵심 아님)

- [ ] 서버 재시작 때 `running`으로 남은 job을 failed로 표시 — **운영 위생.** 조사 “똑똑해짐”과 무관. UI가 영원히 돌 때만 거슬림
- [ ] 비교 결과 화면 / 조사 취소 버튼 UI
- 공용 인덱싱·본문 글자 일치·배포 게이트 — **안 함**

### P3 — 문서

- [ ] 옛 `prs/*`에 “게이트·shadow 폐기, 문제집은 11번” 한 줄

## 4. 검증 명령

```bash
# FakeList / 단위 중심 (live research 제외) — 최근 기준 291 passed
uv run pytest --ignore=tests/e2e/test_live_research_conversation.py -q

# live (옵션)
RUN_LIVE_RESEARCH_E2E=1 uv run pytest tests/e2e/test_live_research_conversation.py -v -s
```

## 5. 코드 진입점 (리뷰·디버그 순서)

1. `docs/specs/2026-08-03-agentic-rag-vertical-mvp-design.md` — 제품/평가 경계  
2. `research_eligibility.py` → `evidence_need.py` → `chat_service.py`  
3. `research_job_service.py` → `research_job_runner.py` → `research_job_stages.py`  
4. `web_research.py` → `indexing.py` → `retrieval.py` → `turn_evidence.py`  
5. `response_comparison.py` · `models/research.py`  
6. `tests/unit/research/` · `tests/conftest.py` (`chat_app_state` 스텁)

## 6. 새 세션 시작 체크리스트

1. 이 문서 §0 텐션 읽기  
2. `git status` / PR #24 최신 본문 확인  
3. 사용자에게 **다음 목표 하나**만 확인 (스모크 / 테스트 레이스 / restart 정리 / …)  
4. 구현 전 가정을 말하고, 불확실하면 묻기  
5. 검증 명령을 돌린 뒤에만 “고쳤다/통과” 말하기  
6. 커밋은 요청받았을 때만, **메시지 한글**
