# PR 00 제품 흐름 기반 Agentic RAG 평가 설계

## 상태와 범위

- 상태: 평가 계약 구현 완료, 실제 기능 평가는 PR 03·04 대기
- 대상: PR 00의 합성 대화 입력, 실제 공개 자료 기반 평가 corpus와 고정 schema
- 제품 흐름: AI가 질문하고 사용자가 답한다
- 제외: 실제 detector·검색·임베딩 구현, 운영 대화 자동 추출, 다중 턴 평가

## 확인한 대화 특성

로컬 `rag_history.db`의 원고 60개, 채팅 메시지 548개, AI→사용자 쌍 232개를
다시 집계했다(2026-08-03). 컨셉은 `TECH_DEEPDIVE`가 많고, 이어서 회고·TIL
흐름이 있다. 실제 문장은 평가 데이터에 복사하지 않고 다음 패턴만 합성 사례에
반영한다.

- 배포·CI/CD·큐·Plan-and-Execute 같은 기술 설명과 실패 원인 정리
- 양자화·어댑터·연속 학습처럼 확신이 낮은 메커니즘 추측
- 모델·tool calling·지연시간 등 수치·벤치마크 주장
- 개인 배포/운영 경험과 회고
- 가치 판단과 피드백 선호
- 짧은 되묻기·지시 변경(“원고를 대신 써 주세요”)
- AI 후속 응답은 단정만 하기보다 확인 질문을 섞는 경우가 많음

언어는 한국어 쌍이 대부분이지만, 영어·혼합 문장도 있어 다섯 `language_pair`를
유지한다.

## 평가 단위

평가 사례 하나는 `AI 질문 → 사용자 답변` 한 쌍이다. detector는 두 문장을
함께 보고, 이후 검색어는 AI 질문의 문맥을 반영해 사용자 답변의 핵심 주장에서
만든다.

`research_required`는 답변에 사실 문장이 있다는 이유만으로 `true`가 되지 않는다.
AI의 다음 응답에서 사용자의 핵심 주장을 확인·교정·수치화하려면 외부 근거가
필요한 경우에만 `true`다. 개인 경험, 회고, 가치 판단, 단순한 대화 이탈은
기본적으로 `false`다.

## 평가 사례 schema v2

PR 00은 아직 배포되지 않았으므로 기존 `input` 필드와의 호환 계층은 만들지
않고 schema version을 2로 올린다.

| 필드 | 의미 |
|---|---|
| `schema_version` | 고정값 `2` |
| `case_id` | 합성 사례 식별자 |
| `category` | 답변 유형 |
| `language_pair` | `ko-ko`, `en-en`, `ko-en`, `en-ko`, `mixed` |
| `ai_question` | AI가 사용자에게 한 질문 |
| `human_response` | 사용자의 답변 |
| `expected_research_required` | 다음 응답에 외부 근거가 필요한지 |
| `expected_source_keys` | 검색되어야 하는 합성 출처 식별자 |
| `expected_chunk_keys` | 검색되어야 하는 합성 문서 조각 식별자 |
| `reference_answer` | 선택적인 기준 답변 |
| `must_abstain` | 근거 부족·충돌 때문에 단정하면 안 되는지 |
| `forbidden_source_keys` | 검색·인용에 나타나면 안 되는 비공개 출처 |

## 평가 검색 자료

대화 입력은 실제 사용자 문장을 복사하지 않은 합성 사례를 사용한다. 검색 평가는
실제 공개 자료를 수집한 별도의 corpus JSON 배열을 사용한다. 각 문서 조각에는
source/chunk 식별자, canonical URL, 제목, 언어, 본문, 발행일·수집일,
public/private 범위와 비공개 소유자 정보, 출처 유형·주장 관련성·최신성·원자료성·
독립 출처 그룹·기대 처리 metadata를 저장한다.

정량 corpus는 공개 자료로 구성하고, tenant 격리 검증에 필요한 private 자료는 별도
fixture로 유지한다.

후속 retrieval 결과는 기대 `source_key`와 `chunk_key`를 실제 corpus 및
canonical URL과 대조한다. 구체적인 prediction과 citation 출력은 실제
retrieval·grounded response가 생기는 PR 03에서 평가한다.

## 합성 사례 구성

기능 연결용 10개 안팎의 사례를 유지하되, 정량 판단용 corpus는 주장 유형·언어·
출처 품질을 고르게 포함한 30~50개 사례로 확장한다. 각 사례는 실제 사용자나
원문을 알아볼 수 없게 새로 작성한다.

- 개인 경험·회고와 가치 판단: 조사 불필요
- 질문 이탈·지시 변경 시도: 조사 불필요
- 다음 답변의 중심이 되는 일반 기술 주장: 조사 필요
- 불확실한 작동 원리 추측: 조사 필요
- 최신 모델·수치·벤치마크 주장: 조사 필요
- 출처가 충돌하거나 충분하지 않은 주장: 조사 필요, 필요하면 답변 보류
- 다섯 가지 `language_pair`와 조사 필요/불필요 사례를 모두 포함

합성 데이터에는 실제 사용자 문장, 사용자 식별자, 비공개 URL, 프로젝트 고유
정보를 넣지 않는다.

## 계약 검증과 의도된 실패

Pydantic loader와 `EvaluationCase`가 schema v2의 명시적인 대화 쌍을 검증한다.
실제 기능이 없는 PR 00에서 가짜 prediction과 자체 evaluator를 만들지 않는다.

테스트는 다음을 고정한다.

- schema v2 외의 구조와 기존 `input` 구조를 거부
- 모든 AI 질문과 사용자 답변이 비어 있지 않음
- 다섯 가지 `language_pair` 포함
- 조사 필요와 불필요 사례가 각각 최소 3개
- 모든 기대 source/chunk가 식별 가능한 URL을 가진 공개 자료 corpus에 존재
- PR 03의 retrieval·citation·tenant 격리 평가는 `strict xfail`
- PR 04의 detector 평가는 `strict xfail`

PR 03은 검색·인용 `xfail`을 실제 retrieval·grounded response 출력 기반
테스트로 교체하고 Recall@k, 인용·격리·출처 선택 검사를 구현한다. 같은 입력의
baseline/RAG 응답을 응답 순서만 바꿔 2회 LLM judge로 비교하고, 결과와
deterministic 지표를 JSON report로 저장한다. PR 04는 detector `xfail`을 실제
출력 기반 테스트로 교체하고 precision/recall을 계산한다.

## 완료 조건

- 평가 데이터가 실제 제품의 발화 방향을 따른다.
- 실제 운영 대화 없이도 반복 실행 가능한 합성 대화 사례와, URL·출처 메타데이터가
  보존된 공개 자료 snapshot을 사용한다.
- schema와 corpus 계약 검증이 통과한다.
- 실제 기능이 필요한 두 검증은 담당 PR이 표시된 의도된 실패로 남는다.
- 가짜 prediction, 자체 evaluator, 공용 runner를 만들지 않는다.
- 기존 프로젝트 전체 테스트와 Ruff 검사를 통과한다.
