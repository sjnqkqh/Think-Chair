# 작업 3 — 근거 검색과 grounded response

[전체 계획](README.md) · [사전 결정 사항](00-preimplementation-decisions.md)

## 목적

research agent 없이 평가 corpus만으로 검색과 인용 응답의 계약을 검증한다. 같은
입력에서 기존 baseline과 RAG 응답을 생성·비교해 검색 품질뿐 아니라 구체성과
자연스러움의 사용자-visible 효과까지 PR 03에서 판정한다.

## 작업 선행 조건

- 작업 2

결정 게이트는 [사전 결정 사항](00-preimplementation-decisions.md)의 PR별 표를 따른다.

## PR 단위

- [PR 03 — 근거 검색과 출처가 표시된 답변](prs/03-retrieval-response.md)

## 계약

### `retrieve_evidence(EvidenceRequest) -> EvidenceContext`

`EvidenceRequest`

- `user_id: UUID`
- `manuscript_id: UUID`
- `query: str`
- `limit: int`

`EvidenceContext`

- `items: list[EvidenceItem]`
  - `chunk_id`, `source_id`, `excerpt`, `score`
  - `title`, `url`, `language`, `published_at`, `fetched_at`
  - `source_type`, `claim_relevance`, `freshness`, `is_primary_source`
  - `independence_group`, `expected_treatment`
- `sufficiency: EvidenceSufficiency`
  - `sufficient: bool`
  - `missing_aspects: list[str]`
  - `supporting_chunk_ids: list[str]`
  - `reason_code: str`
- `is_grounded: bool`
- `warning_code: str | None`

### `generate_grounded_response(GroundedResponseRequest) -> GroundedResponseResult`

`GroundedResponseRequest`

- `phase: Literal["say", "feedback"]`
- `conversation_context: str`
- `evidence: EvidenceContext`

`GroundedResponseResult`

- `text: str`
- `citations: list[Citation]`
  - `source_id`, `chunk_id`, `url`
- `is_grounded: bool`
- `warning_code: str | None`

## 구현 범위

- global public corpus와 허용된 private corpus를 함께 검색
- private corpus는 similarity search 전에 tenant metadata filter 강제
- 사용자 원문 query를 한 번 검색하고 언어 필터는 기본 적용하지 않음
- measured sufficiency가 부족하면 `insufficient`를 반환해 bounded web research로 넘김
- excerpt와 provenance를 함께 반환
- 검색 원문을 system instruction과 분리된 참고 자료로 전달
- citation ID가 실제 `EvidenceItem`에 존재하는지 검증
- 근거 없음·부분 근거·충분한 근거 처리
- 잘못된 인용은 한 번만 재생성하고 재실패 시 non-grounded fallback
- source-quality metadata를 반영해 더 강한 출처와 독립 출처를 우선 선택
- 평가 사례마다 동일 입력으로 baseline/RAG 응답을 생성
- 응답 순서를 바꾼 양방향 pairwise judge 실행과 `unstable` 판정
- deterministic evaluator로 Recall@k, 인용 정확성, 출처 선택, 금지 출처·tenant 격리,
  사용자 자료 유출 및 근거 없는 주장 비율을 계산
- 승·무·패와 구체성·자연스러움 결과를 JSON report로 저장

## 예상 파일

- `app/research/retrieval.py`
- `app/research/grounded_response.py`
- `app/graph/prompts/phases/evidence.py`
- `tests/unit/research/test_retrieval.py`
- `tests/unit/research/test_grounded_response.py`
- `tests/unit/evaluation/test_agentic_rag_eval.py`
- `scripts/run_agentic_rag_eval.py` 또는 기존 평가 runner 위치

## 완료 조건

- seeded chunks에서 기대 source 검색
- public source는 언어·사용자별 vector 복제 없이 재사용
- private source의 cross-user/cross-manuscript 결과 0건
- `ko→ko`, `en→en`, `ko→en`, `en→ko`, mixed query retrieval 평가
- 원문 query가 기준을 통과하면 translation query 0회
- 인용 URL과 excerpt가 저장 source와 일치
- invalid citation이 사용자 응답에 노출되지 않음
- empty retrieval에서 fabricated citation 0건
- 기대 chunk의 Recall@k와 기대 근거 검색 성공률을 계산
- 실제로 사용한 citation의 source/chunk ID·URL·excerpt가 EvidenceContext와 일치
- 더 강한 출처가 있는 사례에서 강한 출처 선택률을 계산
- baseline/RAG pairwise 결과와 deterministic 지표를 저장
- 아래 사전 고정 게이트를 모두 충족
  - RAG 전체 승률 `>= 60%`
  - 구체성 승률 `>= 65%`
  - 자연스러움 패배율 `<= 15%`
  - 평가 순서에 따른 판정 뒤집힘 비율 `<= 10%`
  - 기대 근거 검색 성공률 `>= 80%`
  - 강한 출처 선택률 `>= 80%`
  - 잘못된 인용·금지 출처 노출·사용자 자료 유출 `0건`
- 게이트 미충족 시 PR 04~06으로 진행하지 않고 검색·출처 순위·프롬프트·자연스러움을
  먼저 수정
- 기존 non-research prompt 출력 계약 회귀 없음

## 제거 조건

retrieval과 evidence prompt를 제거하면 기존 `converse`/`feedback` 경로로 돌아갈 수 있어야 한다.
