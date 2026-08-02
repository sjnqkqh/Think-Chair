# 작업 5 — 연구 필요성 감지와 job dispatch

[전체 계획](README.md) · [사전 결정 사항](00-preimplementation-decisions.md)

## 목적

기존 사용자 의도를 유지하면서 연구 필요성을 별도 판단하고 중복 없는 job을 생성한다.

## 작업 선행 조건

- detector는 독립 구현 가능
- dispatcher는 작업 4 필요
- PR 03 baseline/RAG 평가 게이트 통과 후 진행

결정 게이트는 [사전 결정 사항](00-preimplementation-decisions.md)의 PR별 표를 따른다.

## PR 단위

- [PR 04 — 조사 필요 여부 판단과 shadow 평가](prs/04-evidence-detector.md)
- [PR 05 — 조사 실행과 작업 예약](prs/05-research-runner.md)

## 계약

### `detect_evidence_need(...) -> EvidenceNeedDecision`

- `required: bool`
- `claim_or_query: str | None`
- `reason_code: str`
- `confidence: float`

### `dispatch_research(ResearchRequest) -> ResearchJob`

- job을 DB에 먼저 저장
- `message_id` unique conflict에서는 기존 job 반환
- `BackgroundTaskRegistry`에는 `research_job_id` 실행만 예약

## 구현 순서

1. PR 03 baseline/RAG 평가 게이트 통과 여부 확인
2. detector를 live route 밖에서 shadow evaluation
3. 오탐·누락 기준 확인
4. dispatcher 구현
5. 작업 6 전까지 live API에는 연결하지 않음

## 규칙

- `research_required`는 `UserAction`이 아니다.
- 한 message는 최대 한 job만 만든다.
- job 생성 전에 user/manuscript ownership을 재확인한다.
- registry를 job 상태의 source of truth로 사용하지 않는다.
- startup에서 남은 non-terminal job은 `failed/restart_interrupted`로 종료한다.
- 중단된 job은 재시도하지 않으며 사용자가 질문을 다시 입력하면 새 job을 만든다.
- soft-deleted manuscript에는 dispatch하지 않는다.

## 완료 조건

- 일반 대화는 `required=false`
- 최신 수치·출처·공식 문서가 필요한 메시지는 `required=true`
- 동일 message 중복 dispatch 0건
- 타인 소유 또는 삭제된 manuscript dispatch 거부
- non-research chat 회귀 없음

## 제거 조건

detector와 dispatcher를 제거해도 기존 intent router의 action 계약이 변하지 않아야 한다.
