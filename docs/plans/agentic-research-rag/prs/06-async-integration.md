# PR 06 — 메인 채팅과 비동기 결과 전달

[PR 목록](README.md) · [기능 계획](../06-async-integration.md)

## 상태

**D4 확정. PR 03과 PR 05 완료 후 구현**

## 목표

웹 조사가 필요한 턴을 메인 채팅에 연결하고, 준비된 근거를 사용자에게 선택한
방식으로 전달한다.

## 선행 조건

- PR 03
- PR 05
- D4~D9 배포 전 확정 계약

## 포함

- composition root의 research graph/service wiring
- evidence retrieval 또는 research resume 경로
- 채팅 SSE의 `research_required` event
- `POST /api/research/jobs`의 `202 Accepted`, stable job ID, status URL
- job status polling과 cancel API
- `근거 준비됨` 상태와 매 턴 인덱스 검색 evidence 사용
- partial, failed, cancelled 사용자 메시지
- 재시작 후 job 상태 조회

## 제외

- 자동 follow-up, push, 현재 답변 수정
- speculative prefetch
- 외부 durable queue

## 예상 변경

- `app/main.py`
- `app/services/chat_service.py`
- `app/graph/chat_graph_runner.py`
- `app/api/endpoints/chat.py`
- `app/api/endpoints/research.py`
- SSE/UI 지점과 E2E 테스트

## 완료 조건

- non-research latency와 SSE 계약 회귀 없음
- SSE 재연결·중복 POST에도 message당 job 1개
- job 소유자만 status/result/cancel endpoint 사용
- 현재 user/manuscript에만 결과 전달
- 완료 시 `근거 준비됨` 상태만 표시하고 자동 메시지 0건
- `failed/restart_interrupted` job 자동 재실행 0건
- 조사 턴과 일반 턴 E2E 통과
- parent wiring 제거만으로 rollback 가능
