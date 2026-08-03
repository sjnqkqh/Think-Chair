# AI 응답 평가 구현 계획

- 작성일: 2026-08-03
- 근거 설계: `docs/specs/2026-08-03-ai-response-evaluation-design.md`
- 목표: 문서 평가와 분리된 `app/evaluation/`에서, 미리 준비한 근거로 “지금 방식 답” vs “근거 참고 답”을 비교하고 리포트를 남긴다.
- 상태: 최소 완료 기준 충족 (2026-08-03 전체 10사례 실행: 치명 실수 0, 승 8 / 무 2 / 패 0)

## 완료 기준

1. `app/evaluation/`에 계약·규칙 검사·나란히 비교·리포트가 있다.
2. 문서 평가(`app/graph/nodes/evaluate.py` 등)를 수정하지 않는다.
3. 예시 소수(기존 PR 00 사례 재사용 가능)로 스크립트 한 번 실행 시 JSON + 요약 파일이 생긴다.
4. 규칙 검사·비교 결과 파싱은 단위 테스트로 검증한다.
5. `uv run ruff check app/evaluation tests/unit/evaluation` 통과.

## 작업 순서

### 1. 계약(형식) 고정

**만들 것**

- `app/evaluation/__init__.py`
- `app/evaluation/contracts.py`

**내용**

- 사례 입력: AI 질문, 사용자 답변, 허용 출처 목록, 금지 출처 목록, 미리 준비한 근거 조각
- 생성 답: 본문, 인용한 출처 ID/URL 목록(있으면)
- 규칙 검사 결과: 통과 여부, 실패 사유 목록
- 비교 결과: 항목별 승자(구체성/자연스러움/정확성), 전체 승자, 짧은 이유, 순서 뒤집힘 여부
- 사례 결과·전체 요약 모델

**확인**

- `tests/unit/evaluation/test_response_comparison_contracts.py`: 필수 필드·잘못된 JSON 거부

기존 `tests/evaluation/agentic_rag_cases.json` / `agentic_rag_corpus.json`은 **입력 데이터로 연결**만 하고, PR 00 schema를 깨지 않는다. 응답 평가 전용 필드가 더 필요하면 `tests/evaluation/`에 응답 평가용 fixture를 추가한다.

### 2. 규칙 검사 (1단계)

**만들 것**

- `app/evaluation/citation_allowance.py`

**검사**

- 인용이 허용 목록에 있는가
- 금지·타 사용자 출처를 가리키지 않는가
- 유령 출처(표시만 있고 목록에 없음)가 아닌가
- 인용한 출처의 페이지 URL이 `cited_urls`와 응답 본문에 모두 있는가

**확인**

- `tests/unit/evaluation/test_citation_allowance.py`: 통과/실패 사례 각각

내용 일치 검사(2단계)는 구현하지 않는다.

### 3. 답 생성기 (평가 전용)

**만들 것**

- `app/evaluation/response_generation.py`

**동작**

- 지금 방식: 대화 맥락만으로 답 생성 (일반 LLM API)
- 근거 참고: 같은 맥락 + 미리 준비한 근거 조각을 프롬프트에 넣어 답 생성
- 채팅 그래프·Agentic RAG 파이프라인에 의존하지 않음
- 생성 모델은 설정으로 교체 가능

**확인**

- 단위 테스트는 LLM을 직접 호출하지 않고, 입력을 프롬프트/메시지로 조립하는 부분만 검증
- 실제 API 호출은 스크립트 수동 실행으로 확인

### 4. 나란히 비교 (LLM 판정)

**만들 것**

- `app/evaluation/response_comparison.py`
- 판정용 프롬프트 (같은 디렉터리 또는 `app/evaluation/prompts.py`)

**동작**

- 두 답을 A/B로 제시하고 구체성·자연스러움·정확성·전체 선호를 JSON으로 받음
- 순서 바꿔 한 번 더 호출
- 전체 선호가 뒤집히면 무승부/불안정
- 판정 모델은 생성 모델과 별도 설정

**확인**

- `tests/unit/evaluation/test_response_comparison.py`: JSON 파싱, 순서 뒤집힘 → 무승부 처리 (가짜 LLM 응답 사용)

### 5. 리포트

**만들 것**

- `app/evaluation/report.py`

**출력**

- 기계용: JSON (사례별 + 전체 요약)
- 사람용: 짧은 마크다운 요약
- 치명 실수 건수, 승·무·패, 항목별 승률, 뒤집힘 비율
- 승률 통과 숫자는 비워 두거나 “미정”으로 표시

**확인**

- 고정된 가짜 사례 결과로 JSON/마크다운 스냅샷 수준 검증

### 6. 실행 스크립트

**만들 것**

- `scripts/run_ai_response_comparison.py` (디렉터리 없으면 생성)

**동작**

1. fixture 로드
2. 사례마다 두 답 생성 → 규칙 검사 → 나란히 비교
3. `artifacts/ai_response_comparison/`(또는 동일 목적 경로)에 결과 저장
4. 치명 실수 건수를 종료 코드/요약에 명시 (0이 아니면 실패로 볼 수 있게)

**확인**

- 소수 사례(1~3개)로 dry-run 가능하면 `--limit` 지원
- API 키 없을 때는 명확히 실패 메시지

### 7. 설정

**손댈 곳**

- `app/core/config.py`에 응답 평가용 생성/판정 모델·API 설정 추가 (기존 DeepSeek 문서 평가 설정과 이름 분리)

문서 평가 환경 변수를 재사용하지 않는다. 판정 전용 설정을 둔다.

## 의도적으로 나중에 할 일

- 실제 대화 응답 실시간 평가·DB 저장
- 출처 내용 일치 검사
- 승률 숫자 게이트 확정
- 검색 Recall 집계와의 통합 대시보드
- Cursor SDK 판정기
- 30~50개 corpus 확장 (이 계획의 최소 실행 이후)

## 구현 시 주의

- `app/evaluation/` 밖 채팅 노드·문서 평가 코드를 리팩터하지 않는다.
- 답 형태(질문/설명) 분류기를 만들지 않는다.
- 검색 품질 지표와 응답 비교 리포트를 한 파일에 섞지 않는다.

## 권장 진행 단위 (PR/커밋 감각)

1. 계약 + 규칙 검사 + 테스트  
2. 비교 판정 + 리포트 + 테스트  
3. 답 생성기 + 스크립트 + 소수 fixture 연결  

한 PR에 다 넣어도 되지만, 리뷰가 부담되면 위 세 덩어리로 나눈다.
