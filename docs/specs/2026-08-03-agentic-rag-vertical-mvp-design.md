# Agentic RAG 세로 MVP 설계

- 작성일: 2026-08-03
- 상태: 세로 MVP 구현이 브랜치에 모인 상태. 완료·남은 일·작업 텐션은 핸드오프 문서 기준.
- 관련:
  - `docs/plans/agentic-research-rag/09-agentic-rag-vertical-mvp.md`
  - `docs/plans/agentic-research-rag/10-vertical-mvp-handoff.md`
  - `docs/plans/agentic-research-rag/README.md`
  - `docs/plans/agentic-research-rag/00-preimplementation-decisions.md` (D4, D5)
  - `docs/specs/2026-08-03-ai-response-evaluation-design.md`
  - `docs/plans/agentic-research-rag/07-evaluation-continuation.md`

## 1. 목적

문서에 나뉜 PR 03~06을 한 번에 완벽히 다듬지 않고, **채팅에서 직접 써 볼 수 있는 비동기 웹 근거 조사 한 줄**을 만든다.

핵심 쟁점은 “RAG(근거)를 붙이면 AI 답이 얼마나 나아지는가”이다. 조사 job이 끝날 때 **근거 없는 답(baseline)** 과 **근거 있는 답(grounded)** 을 둘 다 만들어 DB에 저장하고, LLM으로 나란히 비교한 결과도 남긴다. 승률 숫자로 배포를 막지는 않는다.

## 2. 확정한 선택

| 항목 | 선택 |
|---|---|
| 진행 단위 | 세로 한 줄 MVP (안 2). PR 03→06을 최소 구현으로 한 흐름에 연결 |
| 사용 방식 | 실제 채팅에 연결 |
| 결과 전달 | 비동기 (D4). 현재 턴은 근거 없이 이어가고, 완료 시 `근거 준비됨`만 표시 |
| 조사 범위 | 웹 조사 포함. 기존 인덱스 검색 후 부족하면 검색·수집·인덱싱 |
| 승률 게이트 | **사용하지 않음.** 비교·점수는 관측용 저장만. 배포/PR을 숫자로 막지 않음 |
| 쌍 평가 시점 | job 제품 완료 후 best-effort로 저장 (화면에는 답 자동 수정 없음). 대화 근거는 매 턴 인덱스 검색 |
| 대화 근거 사용 | prepared JSON 소비 없음. 딥다이브·수업 자료 턴마다 Chroma에서 검색해 프롬프트에 주입 |
| 정량 문제집 | **서비스 성장 관측**: 고정 일반론 → 제품 노드 응답 → Judge 절대 점수 → MD 시계열. 게이트 아님. → `11-rag-judge-corpus-plan.md` (pairwise “근거 유무 비교”와 구분) |

## 3. 범위

### 포함

1. 조사 필요 여부 최소 판단 (`UserAction`에 섞지 않음)
2. 채팅 SSE의 `research_required` 신호
3. `POST /api/research/jobs` → `202` + 안정적 job ID + 상태 URL (메시지당 job 1개)
4. 백그라운드 job: 인덱스 검색 → 부족 시 웹 검색·수집·인덱싱 → 재검색
5. job 제품 완료(수집·인덱싱·상태) 후 baseline / grounded·비교는 평가용으로 best-effort 저장
6. 규칙 검사 + LLM 나란히 비교 결과를 DB에 저장 (`app/evaluation/` 재사용). 제품 handoff와 테이블 분리
7. 클라이언트의 상태 폴링과 `근거 준비됨` 표시 (job `completed`/`partial`)
8. 이후 사용자 턴마다 인덱스 검색으로 근거를 프롬프트에 사용 (일회성 소비 없음)

### 제외

- 승률·Recall 등 숫자로 PR/배포를 막는 게이트 (**계약에서 폐기**)
- detector shadow 로깅·대시보드 (원했던 것은 Route 이후 **실제 RAG 응답**, shadow가 아님)
- 현재 답변 자동 수정, 푸시, 자동 후속 메시지
- 외부 작업 큐, PDF/JS 렌더링 수집
- 출처 본문과 인용 문장의 글자 단위 내용 일치 검사

### 별도 추적 (제품 E2E와 분리)

- 서비스 성장 관측용 Judge **정량 문제집 30~50** → `docs/plans/agentic-research-rag/11-rag-judge-corpus-plan.md`

## 4. 한 바퀴 흐름

```text
사용자 메시지
  → (딥다이브·수업 자료) 매 턴 인덱스 검색 → 근거 텍스트를 대화 프롬프트에 주입
  → 조사 필요 판단
  → (필요 시) SSE research_required + 현재 턴은 단정 피하며 대화 계속
  → 클라이언트 POST /api/research/jobs (202, job_id)
  → 백그라운드(제품):
        기존 인덱스 검색
        → 부족하면 웹 검색·수집·인덱싱
        → 다시 검색해 EvidenceContext 확정
        → job 상태 completed/partial/failed
  → 백그라운드(평가, best-effort):
        baseline / grounded 생성·비교 저장 (제품 완료와 분리)
  → 클라이언트 폴링 → job 성공 시 「근거 준비됨」만 표시
  → 이후 턴도 같은 인덱스 검색으로 근거 사용
```

사용자에게 보이는 말풍선과 DB의 baseline/grounded 비교 기록은 분리한다. 비교용 두 답은 채팅 히스토리에 그대로 올리지 않는다. 근거 JSON을 한 번 쓰고 폐기(consume)하지 않는다.

## 5. 계약 요약

### 조사 job

- 기존 `ResearchJob` / `ResearchJobStatus` 재사용
- `message_id` unique로 중복 생성 방지
- 소유자(`user_id` + `manuscript_id`)만 상태·결과·취소 가능
- 앱 재시작으로 끊긴 job은 `failed` + `restart_interrupted` 계열로 표시, 자동 재실행 없음

### 근거 검색·인용 응답

- `retrieve_evidence(EvidenceRequest) -> EvidenceContext` (작업 3 계약 최소 구현)
- `generate_grounded_response(...)` 로 grounded 본문·citation 생성
- baseline은 동일 대화 맥락·근거 없이 생성
- citation은 EvidenceContext 밖 ID/URL 노출 금지 (기존 규칙 검사 유지)

### 런타임 비교 저장

문서 평가(`document_evaluations`)와 분리된 테이블(가칭 `response_comparison_records` 또는 job 하위 테이블)에 저장한다.

최소 필드:

- `research_job_id`
- `manuscript_id`, `user_id`, `message_id`
- `baseline_body`, `baseline_cited_source_keys`, `baseline_cited_urls`
- `grounded_body`, `grounded_cited_source_keys`, `grounded_cited_urls`
- `baseline_citation_passed`, `grounded_citation_passed`, 실패 사유
- pairwise: 구체성·자연스러움·정확성·전체 승자, 이유, `order_flipped`
- 생성·판정 시각, 사용 모델명

생성·비교가 실패해도 조사 job 완료와 분리해, 채팅 폴링이 막히지 않게 한다. (예: job은 completed, 비교 레코드는 실패/부분 기록 또는 없음)

비교 테이블에는 제품 handoff 필드(`prepared_evidence_json`, `consumed_at`)를 두지 않는다.

## 6. 배치

```
app/research/
  retrieval.py              # 근거 검색
  grounded_response.py      # 인용 응답
  evidence_need.py          # 조사 필요 최소 판단 (이름 확정은 구현 시)
  research_job_runner.py    # job 실행 오케스트레이션

app/evaluation/             # 기존 비교·규칙 검사 재사용
  (+ 런타임 저장 어댑터/서비스는 evaluation 또는 services에 얇게)

app/api/endpoints/
  research.py               # jobs create/status/cancel
  chat.py                   # SSE research_required 추가

app/services/
  chat_service.py           # 턴 정책·매 턴 인덱스 검색 근거 주입

app/models/                 # job 연계 비교 저장 모델
```

엔드포인트는 얇게, 도메인 로직은 서비스/`app/research`·`app/evaluation`에 둔다.

## 7. 완료 기준 (이번 MVP)

1. 조사 필요 턴에서 `research_required`가 나가고 job이 생성된다.
2. job이 웹 조사까지 포함해 근거를 준비하거나, 부족/실패를 상태로 남긴다.
3. job 완료 후 baseline·grounded·비교 판정이 DB에 남는다.
4. UI는 `근거 준비됨`만 보이고, 현재 답을 고치거나 자동 후속 메시지를 보내지 않는다.
5. 이후 사용자 턴에서 인덱스 검색으로 근거를 사용한다(일회성 소비 없음).
6. private 자료 cross-user 결과 0, EvidenceContext 밖 citation 0.
7. 기존 비조사 채팅·문서 생성 경로 회귀 없음.
8. 승률 숫자 게이트는 **두지 않는다** (관측·문제집 측정과 무관하게 배포를 막지 않음).

## 8. 의도적으로 나중 / 별도 문서

- 서비스 성장 관측용 정량 문제집 30~50 → `11-rag-judge-corpus-plan.md`
- 출처 내용 글자 일치 검사 (필수로 보지 않음)
- 비교 결과 admin/화면
- 외부 durable queue
- 서버 재시작 시 미완료 job 표시 정리 (아래 핸드오프 참고)

## 9. 구현 시 주의

- `research_required`를 `UserAction`에 넣지 않는다.
- 비교용 두 답을 사용자 채팅 메시지로 저장하지 않는다.
- 기존 `app/evaluation/`의 계약·규칙 검사·pairwise를 재사용하고, 문서 평가 코드와 섞지 않는다.
- PR 경계를 문서와 다르게 묶는 MVP이므로, 구현 계획에 “문서 PR 03~06 대비 축소·연결 지점”을 명시한다.
