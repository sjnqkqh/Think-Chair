# Agentic RAG 공용 평가 기준 추가

## PR 개요

- 이후 Agentic RAG 기능을 기존 방식과 같은 입력으로 비교하기 위한 공용 평가 기준 추가
- AI 질문과 사용자 답변을 분리한 schema v2 합성 사례 10개로 실제 제품 흐름 반영
- URL·본문·언어·날짜·소유 범위를 가진 합성 source/chunk corpus 추가
- detector precision/recall과 source·chunk Recall@k를 계산하는 결정적 평가 runner 추가
- source·chunk·URL이 맞지 않는 인용, 다른 사용자의 자료 노출, 필요한 답변 보류 누락을 코드로 실패 처리
- baseline과 candidate 결과를 같은 machine-readable JSON 구조로 출력

## 주요 변경 파일

- `tests/evaluation/agentic_rag_cases.json`: detector·retrieval·citation·tenant 격리·자료 충돌 평가 사례 정의
- `tests/evaluation/agentic_rag_corpus.json`: 실제 사용자 자료를 사용하지 않는 검색·인용 평가용 합성 corpus
- `tests/evaluation/run_agentic_rag_eval.py`: 평가 데이터와 예측 결과 로드, metric 계산, 안전성 검사, JSON 요약 출력
- `tests/unit/evaluation/test_agentic_rag_eval.py`: 스키마 고정, metric 계산, 안전성 실패, baseline/candidate 출력 계약 검증

## 비고

- `uv run pytest -q`: 181개 통과
- `uv run pytest tests/unit/evaluation/test_agentic_rag_eval.py -q`: 8개 통과
- `uv run ruff check app tests`: 통과
- 외부 평가 서비스, 신규 패키지 설치, 환경 변수, DB migration, runtime 연결 없음
- 기존 환경의 `StarletteDeprecationWarning` 1건 유지
