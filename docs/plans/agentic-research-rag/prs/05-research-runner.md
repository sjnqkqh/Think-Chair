# PR 05 — 조사 실행과 작업 예약

[PR 목록](README.md) · [기능 계획](../04-research-subgraph.md) · [감지·작업 생성 계획](../05-detection-dispatch.md)

## 목표

검출 결과를 중복 없는 `ResearchJob`으로 저장하고, 검색·수집·인덱싱을 제한된
범위 안에서 실행하는 독립 조사 기능을 만든다.

## 선행 조건

- PR 03 및 baseline/RAG 평가 게이트 통과
- PR 04
- D5, D6, D8, D9

## 포함

- `dispatch_research(ResearchRequest) -> ResearchJob`
- `message_id` unique constraint와 user/manuscript ownership 확인
- job 저장 후 `BackgroundTaskRegistry` 실행 예약
- research state, nodes, builder, runner
- job별 checkpoint namespace와 `thread_id=research_job_id`
- 기존 corpus retrieval과 sufficiency 판정
- 근거가 부족할 때만 query planning과 search/fetch tool loop
- 저장된 URL 재사용과 새 source의 `index_sources` 호출
- round/query/source/deadline 예산
- 실행 상태와 `sufficient | insufficient` 근거 결과 분리
- startup·shutdown·cancel·deadline의 terminal 상태 처리

## 제외

- parent chat graph 연결
- polling 또는 push API
- 사용자 결과 전달과 UI

## 예상 변경

- `app/graph/research/`
- `app/graph/research_graph_runner.py`
- `app/services/research_service.py`
- research repository의 dispatch 경계
- `tests/unit/research/test_research_graph.py`

## 완료 조건

- 같은 message에서 중복 job 0건
- 타인 소유·삭제된 manuscript 거부
- scheduler 실패가 persisted job에 안전한 상태로 남음
- tool-call loop와 모든 terminal 상태 테스트
- 충분한 기존 evidence에서 web tool call 0회
- 검색 결과가 모두 기존 URL이면 fetch call 0회
- 정상적인 근거 부족을 시스템 장애로 재시도하지 않음
- job 간 checkpoint 격리
- 재시작 후 남은 job을 `failed/restart_interrupted`로 끝내고 재실행하지 않음
- shutdown·cancel·deadline이 정해진 terminal error code로 저장됨
- tool failure가 parent chat graph에 전파되지 않음
- configured provider의 credentialed smoke test 경로 존재
