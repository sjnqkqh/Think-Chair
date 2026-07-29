# Agentic RAG 평가 계약과 사례 추가

## PR 개요

- 이후 Agentic RAG 기능을 같은 입력과 기대 결과로 검증하기 위한 공용 평가 계약 추가
- AI 질문과 사용자 답변을 분리한 schema v2 합성 사례 10개로 실제 제품 흐름 반영
- URL·본문·언어·날짜·소유 범위를 가진 합성 source/chunk corpus 추가
- 실제 구현이 없는 detector·retrieval 평가는 담당 PR이 표시된 `strict xfail`로 기록
- PR 03에서 retrieval·citation·tenant 격리 평가를, PR 04에서 detector 평가를 실제 출력 기반 테스트로 전환
- 테스트가 가짜 prediction을 만들거나 자체 evaluator를 검증하지 않도록 runner 제거

## 주요 변경 파일

- `tests/evaluation/agentic_rag_cases.json`: detector·retrieval·citation·tenant 격리·자료 충돌 평가 사례 정의
- `tests/evaluation/agentic_rag_corpus.json`: 실제 사용자 자료를 사용하지 않는 검색·인용 평가용 합성 corpus
- `tests/evaluation/agentic_rag_eval_contracts.py`: 고정 schema와 합성 사례·corpus 참조 검증
- `tests/unit/evaluation/test_agentic_rag_eval.py`: 계약 검증과 PR 03·04가 성공으로 바꿀 의도된 실패

## 비고

- `uv run pytest tests/unit/evaluation/test_agentic_rag_eval.py -rxX`: 5개 통과, 의도된 실패 2개
- `uv run pytest`: 178개 통과, 의도된 실패 2개
- `uv run ruff check app tests`: 통과
- 외부 평가 서비스, 신규 패키지 설치, 환경 변수, DB migration, runtime 연결 없음
- 기존 환경의 `StarletteDeprecationWarning` 1건 유지
