# Agentic RAG 평가 의사결정 및 다음 세션 인수인계

작성일: 2026-08-02
상태: 평가 우선순위와 PR03 완료 게이트 확정. PR03 최소 구현 및 평가 corpus 확장은 다음 작업.

## 1. 핵심 결론

전체 Agentic RAG(PR04~06)를 먼저 완성하지 않는다. 먼저 PR03의 검색→근거 응답 최소 경로를 구현하고, 기존 응답(baseline)과 RAG 응답을 같은 입력에서 비교한다. RAG가 실제 제품 가치를 개선한다는 증거가 있을 때만 웹 검색·서브에이전트·비동기 연결로 확장한다.

평가가 없다면 Agentic RAG를 우선적으로 크게 만들 이유가 약하다. 검색 Recall만 좋아져도 답변이 더 구체적·유용해진다는 보장은 없으므로, 검색 품질과 사용자-visible 효과를 분리해서 측정한다.

## 2. 제품 승리 조건

사용자의 일반적인 주장/아이디어를 근거, 수치, 사례로 구체화하면서 대화 흐름과 자연스러움을 해치지 않는 것.

## 3. 평가 방식

LLM judge가 baseline과 RAG 응답을 pairwise로 비교한다. 응답 순서만 바꾸어 각 사례를 2회 평가하고, 결과가 뒤집히면 `tie/unstable`로 기록한다. 별도 정식 admin 페이지는 만들지 않는다.

판정 책임은 분리한다.

- 코드로 확정: 검색 적중/Recall@k, citation ID·URL 일치, 금지 출처 노출, 사용자 자료 유출, 근거 없는 주장 비율(가능한 범위).
- LLM judge: 구체성, 근거를 활용한 전체 품질, 대화 자연스러움, baseline 대비 선호.

정량 집계 항목:

- RAG 전체 승·무·패 비율
- 구체성 승률
- 자연스러움 패배율(비열화율)
- Retrieval Recall@k
- 인용 정확률
- 금지 출처/사용자 자료 유출 건수
- 근거가 뒷받침하지 않는 주장 비율
- 더 강한 출처가 있을 때 강한 출처를 선택한 비율
- 평가 순서에 따른 판정 뒤집힘 비율

## 4. 평가용 corpus 원칙

완전한 가상 문서가 아니라 실제 공개 자료를 수집한다. 신뢰도가 다른 자료를 의도적으로 함께 포함해 자료 선택 능력까지 평가한다.

각 문서에 다음 메타데이터를 붙인다.

- 출처 유형: 공식, 논문/벤치마크, 벤더, 전문 매체, 커뮤니티
- 주장과의 직접 관련성
- 발행일/최신성
- 원자료인지 재인용인지
- 독립 출처와의 일치 또는 충돌
- 기대 처리: 우선 사용, 보조 사용, 제외

저장 단계에서는 안전성, 출처 식별 가능성, 본문 추출 가능성만 검사한다. 질문별 검색 단계에서 관련성·출처 유형·최신성·원자료성·독립 출처 일치 여부를 반영해 순위를 조정한다.

Reddit·댓글·개인 블로그 같은 커뮤니티 자료도 허용한다. 다만 공식 자료가 없을 때 단독 근거가 될 수 있으며, 답변에서는 “사용자 보고/경험 사례”라는 한계를 명시하고 일반적 사실처럼 과도하게 단정하지 않는다.

정량 corpus는 공개 자료로 구성하고, tenant 격리 검증에 필요한 private 자료는 별도
fixture로 유지해 출처 품질 평가와 접근 권한 평가를 섞지 않는다.

## 5. 초기 corpus 규모와 PR03 완료 게이트

기존 합성 사례 10개는 기능 연결용으로 유지한다. 정량 판단용으로 주장 유형·언어·출처 품질을 고르게 포함한 30~50개로 확장한다.

첫 실행 전에 고정하는 PR03 진행/중단 기준:

- RAG 전체 승률 ≥ 60%
- 구체성 승률 ≥ 65%
- 자연스러움 패배율 ≤ 15%
- 순서 뒤집힘 비율 ≤ 10%
- 기대 근거 검색 성공률 ≥ 80%
- 강한 출처 선택률 ≥ 80%
- 잘못된 인용, 금지 출처 노출, 사용자 자료 유출 = 0건

이 기준은 PR 조건이므로 결과를 본 뒤 임의로 낮추지 않는다. 표본이 작으므로
절대적인 통계적 증명이라기보다 PR04~06 진행 여부를 판단하는 초기 게이트로
사용한다.

## 6. 현재 repository에서 확인된 자산

- 평가 설계: `docs/specs/2026-07-29-product-aligned-rag-evaluation-design.md`
- 선행 결정 및 D9 문서 품질 검증 범위: `docs/plans/agentic-research-rag/00-preimplementation-decisions.md`
- PR03 검색/근거 응답 계획: `docs/plans/agentic-research-rag/03-retrieval-response.md`
- PR00 평가 하네스 계획: `docs/plans/agentic-research-rag/prs/00-evaluation-harness.md`
- PR02 인덱싱 계획: `docs/plans/agentic-research-rag/02-indexing.md`
- PR04~06 계획: `docs/plans/agentic-research-rag/04-research-subgraph.md`, `05-detection-dispatch.md`, `06-async-integration.md`
- 기존 평가 코드/테스트로 대화에서 확인된 파일명: `run_agentic_rag_eval.py`, `test_agentic_rag_eval.py` (정확한 경로는 다음 세션에서 `rg --files`로 재확인)

현재 D9는 안전성·파싱 가능성·출처 존재 여부 중심이며, 자료의 신뢰도 자체를 판정하지 않는다. source-quality metadata는 PR02에서 보존하고 PR03 검색 단계에서 출처 선택에 반영한다. PR03은 검색 Recall, 인용 정확성, 사용자 자료 격리와 baseline 대비 구체성·자연스러움 개선을 함께 평가한다.

## 7. 다음 세션 실행 순서

1. 위 기존 문서를 다시 읽고 현재 구현 상태와 테스트 명령을 확인한다.
2. 기존 10개 fixture의 스키마를 보존한 채 30~50개 평가 사례로 확장한다.
3. 실제 공개 자료를 검색·수집해 문서와 메타데이터 fixture를 만든다. 공식/논문/벤더/전문 매체/커뮤니티를 혼합하고, 출처 품질이 상충하는 사례도 포함한다.
4. PR03 최소 경로(검색→retrieved evidence→RAG 응답)를 연결한다.
5. 동일 입력으로 baseline/RAG를 생성하고, 결정적 검사와 양방향 LLM pairwise judge를 실행한다.
6. 승·무·패 및 자동 지표를 리포트로 저장한다.
7. 기준 충족 시 PR04로 진행하고, 미충족 시 Agentic RAG 확장을 멈추고 실패 원인(검색, 출처 순위, 프롬프트, 자연스러움)을 먼저 수정한다.

## 8. 아직 미완료인 것

- 최소 source-quality 점수/순위 공식의 코드화
- 실제 평가 corpus 30~50개 수집
- LLM judge 프롬프트와 JSON 출력 스키마
- PR03 구현 및 end-to-end 실행
- 위 게이트의 실제 측정값

## 9. 세션 환경 메모

대화 transcript 저장과 일부 UserPrompt/PreToolUse hook은 실패했다. 로그에 `guard-destructive.py`, `sync-grok-model-config.py`, `session-intent.py`가 존재하지 않는다는 오류가 있었지만, 이 인수인계 문서는 repository 안에 저장되어 다음 세션에서 직접 읽을 수 있다. 다음 세션 시작 시 hook 상태와 `git status --short`를 먼저 확인한다.
