# PR 00 제품 흐름 기반 Agentic RAG 평가 설계

## 상태와 범위

- 상태: 구현 완료
- 대상: PR 00의 합성 평가 데이터와 평가 runner
- 제품 흐름: AI가 질문하고 사용자가 답한다
- 제외: 실제 detector·검색·임베딩 구현, 운영 대화 자동 추출, 다중 턴 평가

## 확인한 대화 특성

로컬 대화 저장소의 41개 대화와 548개 메시지에서 역할 순서와 답변 유형을
확인했다. 실제 문장은 평가 데이터에 복사하지 않고 다음 패턴만 합성 사례에
반영한다.

- 사용자의 일반적인 기술 설명
- 확신이 낮은 원인 추측
- 최신 모델·수치·벤치마크에 관한 주장
- 개인 경험과 회고
- 가치 판단과 의견
- 질문과 무관한 답변 또는 지시 변경 시도

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

## 합성 검색 자료

검색 평가는 별도의 합성 corpus JSON 배열을 사용한다. 각 문서 조각에는 source/chunk
식별자, canonical URL, 제목, 언어, 본문, 발행일·수집일, public/private 범위와
비공개 소유자 정보를 저장한다. 실제 운영 자료나 URL은 사용하지 않는다.

prediction의 citation은 `source_key`, `chunk_key`, `url`을 한 묶음으로 전달한다.
세 값이 실제 corpus와 일치하고 해당 source/chunk가 검색 결과에 포함된 경우만
유효한 인용으로 인정한다.

## 합성 사례 구성

10개 안팎의 사례로 시작하고, 각 사례는 실제 사용자나 원문을 알아볼 수 없게
새로 작성한다.

- 개인 경험·회고와 가치 판단: 조사 불필요
- 질문 이탈·지시 변경 시도: 조사 불필요
- 다음 답변의 중심이 되는 일반 기술 주장: 조사 필요
- 불확실한 작동 원리 추측: 조사 필요
- 최신 모델·수치·벤치마크 주장: 조사 필요
- 출처가 충돌하거나 충분하지 않은 주장: 조사 필요, 필요하면 답변 보류
- 다섯 가지 `language_pair`와 조사 필요/불필요 사례를 모두 포함

합성 데이터에는 실제 사용자 문장, 사용자 식별자, 비공개 URL, 프로젝트 고유
정보를 넣지 않는다.

## runner와 테스트 변경

runner의 지표 계산 방식은 유지한다. Pydantic loader와 `EvaluationCase`가
schema v2의 명시적인 대화 쌍을 검증한다.

테스트는 다음을 고정한다.

- schema v2 외의 구조와 기존 `input` 구조를 거부
- 모든 AI 질문과 사용자 답변이 비어 있지 않음
- 다섯 가지 `language_pair` 포함
- 조사 필요와 불필요 사례가 각각 최소 3개
- detector precision/recall과 retrieval Recall@k 계산
- 잘못된 인용, 비공개 출처 노출, 답변 보류 실패를 결정적으로 검출
- baseline과 candidate의 CLI 출력 형식이 동일

runner는 이미 생성된 baseline/candidate prediction을 채점한다. 실제 서비스나
외부 모델을 호출해 prediction·응답 시간·비용을 만드는 adapter는 후속 작업이다.

## 완료 조건

- 평가 데이터가 실제 제품의 발화 방향을 따른다.
- 실제 운영 대화 없이도 반복 실행 가능한 합성 사례만 사용한다.
- schema와 runner 테스트가 통과한다.
- 기존 프로젝트 전체 테스트와 Ruff 검사를 통과한다.
