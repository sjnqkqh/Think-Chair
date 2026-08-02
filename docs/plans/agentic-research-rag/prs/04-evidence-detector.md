# PR 04 — 조사 필요 여부 판단과 shadow 평가

[PR 목록](README.md) · [기능 계획](../05-detection-dispatch.md)

## 목표

사용자 의도와 별개로 외부 근거가 필요한 메시지를 판단하고, 실제 사용자 동작은
바꾸지 않은 채 정확도를 측정한다.

## 선행 조건

- PR 00
- PR 03의 baseline/RAG 평가 게이트 통과
- D7 detector evaluation set
- D8 shadow-log masking·보존 정책

## 포함

- `EvidenceNeedDecision`
- `required`, `claim_or_query`, `reason_code`, `confidence`
- 대표 메시지 evaluation set
- live route 밖 shadow logging
- 오탐·누락 판정 기준
- PR 00 조사 필요 여부 `xfail`을 실제 detector 출력 기반 평가로 교체
- detector precision/recall evaluator
- PR 03 게이트 미충족 시 detector 구현을 진행하지 않고 PR 03 원인 수정

## 제외

- `ResearchJob` 생성
- background 실행
- 사용자 응답 변경

## 예상 변경

- evidence detector와 prompt
- detector unit/evaluation test
- `tests/unit/evaluation/test_agentic_rag_eval.py`
- 최소 shadow observation hook

## 완료 조건

- 일반 대화와 근거 필요 메시지의 기준 사례 통과
- PR 00의 조사 필요 여부 `xfail` 0건
- 합성 평가 사례의 precision/recall을 실제 detector 출력으로 계산
- `UserAction` 계약 변경 없음
- detector 실패가 기존 chat을 중단하지 않음
- 조사 작업을 만들 때 사용할 안정된 output contract 확정
