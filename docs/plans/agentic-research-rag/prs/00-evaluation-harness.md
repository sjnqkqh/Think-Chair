# PR 00 — Agentic RAG 평가 계약과 사례

[PR 목록](README.md) · [사전 결정 사항](../00-preimplementation-decisions.md)

## 목표

후속 PR이 같은 입력과 기대 결과로 구현을 검증하도록 평가 데이터와 고정된
계약을 만든다. PR 03이 baseline과 RAG의 사용자-visible 효과까지 같은 입력에서
비교할 수 있도록 deterministic 지표와 pairwise judge 입출력 schema도 고정한다.
아직 실제 기능이 없는 평가는 성공한 것처럼 흉내 내지 않고, 담당 PR이 명시된
`strict xfail`로 남긴다.

## 선행 조건

- 없음

## 포함

- frozen evaluation case schema와 version
- 실제 사용자 문장을 복사하지 않은 `AI 질문 → 사용자 답변` 평가 입력 사례
- 한국어·영어·교차 언어·mixed query 사례
- 일반 대화와 evidence-required detector 사례
- 실제 공개 자료를 기반으로 한 30~50개 평가 사례와 source/chunk corpus
- URL·본문·언어·날짜·소유 범위 및 source-quality 메타데이터
- tenant 격리를 검증하기 위한 최소 private fixture는 공개 자료 정량 corpus와 분리
- invalid citation, tenant leak, stale/conflicting source 사례
- baseline/RAG pairwise judge의 고정 JSON 입력·출력 schema
- 승·무·패, 구체성, 자연스러움, 순서 뒤집힘 및 source 선택 지표의 집계 계약
- PR 03에서 실제 검색·인용 결과로 교체할 `strict xfail`
- PR 04에서 실제 조사 필요 판단 결과로 교체할 `strict xfail`

## 최소 case fields

- `case_id`, `category`, `language_pair`
- `ai_question`, `human_response`
- `expected_research_required`
- `expected_source_keys`, `expected_chunk_keys`
- `reference_answer | None`
- `must_abstain`
- `forbidden_source_keys`

## source-quality metadata

각 corpus chunk에는 다음 값을 기록한다.

- `source_type`: `official | paper_benchmark | vendor | professional_media | community`
- `claim_relevance`: `direct | supporting | unrelated`
- `freshness`: `current | recent | stale | unknown`
- `is_primary_source`: 원자료 여부
- `independence_group`: 같은 원자료를 재인용한 자료를 묶는 식별자
- `expected_treatment`: `preferred | supporting | exclude`

공식·논문·벤더·전문 매체·커뮤니티 자료를 섞고, 출처 품질이나 결론이 충돌하는
사례를 포함한다. 커뮤니티 자료는 공식 자료가 없을 때만 단독 근거가 될 수 있으며,
답변에서 사용자 보고·경험 사례라는 한계를 표시해야 한다. private 자료는
tenant 격리와 유출 방지 검사용으로만 둔다.

## pairwise judge contract

각 사례에 대해 같은 입력으로 baseline과 RAG 응답을 생성하고, 응답 순서를 바꿔
두 번 judge한다. judge 출력은 다음 필드를 포함한다.

- `case_id`, `presentation_order`
- `winner`: `baseline | rag | tie`
- `specificity_winner`: `baseline | rag | tie`
- `naturalness_winner`: `baseline | rag | tie`
- `reason`, `is_valid`

두 평가의 winner가 다르면 `unstable`로 기록한다. judge가 인용·격리·금지 출처를
판정하지 않으며, 해당 항목은 deterministic evaluator가 코드로 계산한다.

## 예상 변경

- `tests/evaluation/agentic_rag_cases.json`
- `tests/evaluation/agentic_rag_corpus.json`
- `tests/evaluation/agentic_rag_eval_contracts.py`
- `tests/unit/evaluation/test_agentic_rag_eval.py`

기존 Pydantic, pytest와 표준 JSON만 사용한다. 외부 평가 서비스 의존성은 추가하지 않는다.

## 제외

- embedding·retrieval 구현
- prediction 생성, 실제 judge provider 호출과 production trace 평가는 제외한다.
- production baseline adapter와 실제 호출 시간·비용 측정
- PR 03의 실제 출력 기반 평가 실행

실제 구현이 없는 상태에서 테스트가 prediction을 만들어 채점하면 평가 코드가
자기 자신만 검증하게 된다. 따라서 PR 00은 입력과 기대 결과만 고정한다.

| 의도된 실패 | 성공으로 바꾸는 PR | 전환 조건 |
|---|---|---|
| 검색·인용·사용자 자료 격리 | PR 03 | 실제 retrieval·grounded response 출력으로 평가하고 placeholder `xfail` 제거 |
| 조사 필요 여부 판단 | PR 04 | 실제 detector 출력으로 평가하고 placeholder `xfail` 제거 |

`strict xfail`은 미완성 기능을 숨기는 예외가 아니다. 담당 PR에서 실제 구현을
연결하지 않은 채 완료할 수 없도록 이름과 전환 조건을 고정하는 임시 계약이다.

## 완료 조건

- `ko→ko`, `en→en`, `ko→en`, `en→ko`, mixed case 포함
- 모든 기대 source/chunk가 식별 가능한 URL을 가진 공개 자료 corpus에 존재
- corpus가 30~50개 사례와 실제 공개 자료로 구성되고 source-quality metadata를 가짐
- schema version과 필수 필드 변경을 deterministic하게 거부
- pairwise judge와 deterministic evaluator의 입출력 schema가 고정됨
- PR 03 게이트 계산에 필요한 baseline/RAG 결과 필드가 고정됨
- 실제 기능이 필요한 평가는 담당 PR이 적힌 `strict xfail`
- 가짜 prediction, 자체 evaluator, 공용 runner 구현 없음
