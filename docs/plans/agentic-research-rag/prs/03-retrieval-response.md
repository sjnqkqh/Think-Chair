# PR 03 — 근거 검색과 출처가 표시된 답변

[PR 목록](README.md) · [기능 계획](../03-retrieval-response.md)

## 목표

질문에 맞는 자료 조각을 찾고, 실제로 찾은 자료만 인용하는 답변까지 한 흐름으로
검증한다. 같은 입력의 baseline/RAG pairwise 평가와 deterministic 검사를 이 PR의
완료 조건에 포함해, PR 04~06 진행 여부를 수치로 결정한다.

## 선행 조건

- PR 02
- D5 evidence sufficiency와 근거 부족 시 동작
- D7 다국어 retrieval·groundedness 평가 기준
- D9 untrusted-context policy

## 포함

- `EvidenceRequest`, `EvidenceItem`, `EvidenceContext`
- public corpus와 허용된 private corpus 검색
- 언어 필터 없는 원문 query 1회와 sufficiency 판정
- source title, URL, 날짜, excerpt 결합
- source type, 관련성, 최신성, 원자료성, 독립 출처 그룹, 기대 처리 metadata 결합
- 공식·논문/벤치마크·벤더·전문 매체·커뮤니티 출처의 품질 순위 반영
- empty retrieval과 stale evidence 처리
- `GroundedResponseRequest`, `Citation`, `GroundedResponseResult`
- 참고 자료와 system instruction 분리
- citation source/chunk ID 검증
- 잘못된 인용 한 번 재생성
- 재실패 또는 근거 없음의 non-grounded fallback
- PR 00 검색·인용·사용자 자료 격리 `xfail`을 실제 출력 기반 평가로 교체
- retrieval Recall@k, 인용·출처 선택·격리 deterministic evaluator
- 동일 입력의 baseline/RAG 응답 생성, 양방향 pairwise judge와 JSON report
- 구체성·자연스러움·승률·순서 뒤집힘 집계

## 제외

- web search fallback
- research job 생성
- parent chat wiring

## 예상 변경

- `app/research/retrieval.py`
- `app/research/grounded_response.py`
- `app/graph/prompts/phases/evidence.py`
- `tests/unit/research/test_retrieval.py`
- `tests/unit/research/test_grounded_response.py`
- `tests/unit/evaluation/test_agentic_rag_eval.py`
- `scripts/run_agentic_rag_eval.py` 또는 기존 평가 runner 위치

## 완료 조건

- seeded query가 기대 source를 반환
- private corpus의 cross-user 결과 0건
- public corpus는 사용자별 vector 복제 없이 재사용
- 저장된 source와 URL·excerpt 일치
- `ko→ko`, `en→en`, `ko→en`, `en→ko`, mixed retrieval gate 통과
- `EvidenceContext` 밖의 citation 노출 0건
- empty evidence에서 fabricated citation 0건
- PR 00의 검색·인용·격리 `xfail` 0건
- 30~50개 평가 사례와 실제 공개 자료 기반 corpus로 평가 실행
- 합성 입력의 retrieval Recall@k라는 기존 계약과 source-quality metadata 기반 강한
  출처 선택률을 실제 구현 출력으로 계산
- baseline/RAG 응답을 같은 입력에서 생성하고 응답 순서를 바꿔 각 사례를 2회 judge
- 아래 게이트를 모두 통과
  - RAG 전체 승률 `>= 60%`
  - 구체성 승률 `>= 65%`
  - 자연스러움 패배율 `<= 15%`
  - 평가 순서에 따른 판정 뒤집힘 비율 `<= 10%`
  - 기대 근거 검색 성공률 `>= 80%`
  - 강한 출처 선택률 `>= 80%`
  - 잘못된 인용·금지 출처 노출·사용자 자료 유출 `0건`
- 게이트 미충족 시 PR 04~06 진행을 중단하고 원인별 수정 계획을 남김
- 기존 `converse`/`feedback` 출력 계약 회귀 없음
