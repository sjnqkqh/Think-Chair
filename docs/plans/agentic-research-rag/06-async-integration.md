# 작업 6 — 메인 채팅과 비동기 결과 전달

[전체 계획](README.md) · [사전 결정 사항](00-preimplementation-decisions.md)

## 상태

**D4 확정. 작업 3~5 완료 후 구현**

## 작업 선행 조건

- 작업 3~5
- PR 03 baseline/RAG 평가 게이트와 PR 04 detector 평가 통과

결정 게이트는 [사전 결정 사항](00-preimplementation-decisions.md)의 PR별 표를 따른다.

## PR 단위

- [PR 06 — 메인 채팅과 비동기 결과 전달](prs/06-async-integration.md)

## 수정 예상 지점

- `app/main.py`: research graph/service wiring
- `app/services/chat_service.py`: turn decision과 delivery policy
- `app/graph/chat_graph_runner.py`: evidence context 주입 또는 research resume
- `app/api/endpoints/chat.py`: SSE의 `research_required` event
- `app/api/endpoints/research.py`: job 생성·상태 조회·취소
- SSE/UI: 상태 polling과 `근거 준비됨` 표시

## 확정 동작

1. 현재 턴은 근거 없는 사실 주장을 피하고 개념적 질문·가정으로 대화를 이어간다.
2. 기존 채팅 API는 SSE 답변 중 `research_required` event로 추가 조사가 필요하다고 알린다.
3. 클라이언트는 별도 `POST /api/research/jobs`를 호출한다.
4. 조사 생성 API는 `202 Accepted`, stable job ID와 status URL을 반환한다.
5. 클라이언트는 status URL을 주기적으로 조회한다.
6. 완료되면 `근거 준비됨` 상태만 표시한다.
7. 현재 답변을 수정하거나 자동 후속 메시지를 보내지 않는다.
8. 다음 사용자 턴부터 완료된 근거를 자동 사용한다.
9. 앱 재시작으로 중단된 job은 `failed/restart_interrupted`로 표시하며 재시도 UI를 제공하지 않는다.

## 완료 조건

- non-research turn latency와 SSE 계약 회귀 없음
- job 상태를 재시작 후에도 조회 가능
- SSE 재연결이나 중복 생성 요청에도 message당 job은 1개
- job 소유자만 상태 조회·취소 가능
- polling 완료 후 `근거 준비됨` 표시
- 완료 전후 자동 follow-up 메시지 0건
- 다음 사용자 턴에서 완료 evidence 사용
- `restart_interrupted` job은 자동 재실행되지 않음
- 근거가 해당 user/manuscript에만 전달
- partial/failed 결과를 안전한 사용자 메시지로 변환
- research-required 턴과 일반 턴 E2E 검증

## 제거 조건

parent wiring만 제거하면 기존 chat path로 즉시 rollback할 수 있어야 한다.
