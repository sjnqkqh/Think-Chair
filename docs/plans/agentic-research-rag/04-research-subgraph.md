# 작업 4 — 독립 리서치 서브그래프

[전체 계획](README.md) · [사전 결정 사항](00-preimplementation-decisions.md)

## 목적

메인 채팅과 별도 checkpoint를 가진 bounded research worker를 만든다.

## 작업 선행 조건

- 작업 1
- 작업 2
- 작업 3의 `retrieve_evidence`
- PR 03 baseline/RAG 평가 게이트 통과

결정 게이트는 [사전 결정 사항](00-preimplementation-decisions.md)의 PR별 표를 따른다.

## PR 단위

- [PR 05 — 조사 실행과 작업 예약](prs/05-research-runner.md)

## 계약

### `ResearchGraphRunner.run(ResearchRequest) -> ResearchResult`

`ResearchRequest`

- job/user/manuscript/message ID
- `topic`, `concept`, `claim_or_message`
- `max_rounds`, `max_queries`, `max_sources`
- `deadline_seconds`

`ResearchResult`

- `status: Literal["completed", "partial", "failed", "cancelled"]`
- `evidence_status: Literal["sufficient", "insufficient"]`
- `indexed_source_ids: list[UUID]`
- `chunk_count: int`
- `warning_codes: list[str]`
- `terminal_error_code: str | None`

## 내부 흐름

```text
plan queries
→ retrieve existing evidence
→ sufficient면 종료
→ insufficient면 search
→ 검색 결과 URL이 저장돼 있으면 기존 source 재사용
→ 처음 보는 URL만 fetch
→ deduplicate and index_sources
→ retrieve final evidence
→ persist terminal job status
```

- graph는 한 번 컴파일하고 job마다 실행한다.
- job-isolated checkpointer namespace를 사용한다. 물리적으로 checkpoint가 남아도 앱 재시작 후 해당 job을 resume하지 않는다.
- 앱 재시작 시 끝나지 않은 job은 checkpoint와 무관하게 `failed/restart_interrupted`로 종료한다.
- checkpoint `thread_id`는 `research_job_id`다.
- 여러 검색어의 worker 분산은 필요할 때 LangGraph `Send`로 제한한다.
- round/query/source/wall-clock 예산을 강제한다.
- 같은 query/result 반복 시 종료한다.
- 정규화한 requested/canonical URL은 public source와 현재 사용자가 소유한 private source에서 먼저 조회하고, 일치하면 `fetch_page`를 호출하지 않는다.
- source admission은 1차 출처, provenance, 발행일·수집일을 우선한다.

## 예상 파일

- `app/graph/research/state.py`
- `app/graph/research/builder.py`
- `app/graph/research/nodes.py`
- `app/graph/research_graph_runner.py`
- `app/services/research_service.py`
- `tests/unit/research/test_research_graph.py`

## 완료 조건

- fake model/tool로 tool-call loop 검증
- configured provider는 credentialed smoke test로 별도 검증
- success, partial failure, total failure 경로 테스트
- 정상 실행 후 evidence 부족은 `completed + insufficient`이며 operational retry하지 않음
- 실행 예산 초과 없음
- 충분한 기존 corpus가 있으면 web tool call 0회
- 검색 결과가 모두 기존 URL이면 fetch call 0회
- 앱 종료 유예 시간이 지나면 `failed/shutdown_interrupted`로 저장됨
- 사용자 취소는 `cancelled/user_cancelled`로 저장됨
- 제한 시간 초과는 `cancelled/deadline_exceeded`로 저장됨
- source 우선순위 검증
- job 간 checkpoint와 상태가 섞이지 않음
- 앱 재시작 후 `failed/restart_interrupted`로 종료되고 resume되지 않음
- tool failure가 parent chat graph를 실패시키지 않음

## 제거 조건

research graph와 runner/service를 제거해도 기존 chat graph가 컴파일되고 동작해야 한다.
