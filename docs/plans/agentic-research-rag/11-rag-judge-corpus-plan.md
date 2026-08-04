# 서비스 성장 관측용 Judge 문제집 계획

- 작성일: 2026-08-04
- 갱신: 2026-08-04 — **의도 확정**: pairwise “근거 유무 비교”가 아니라 **절대 점수 + 시계열로 서비스 성장을 본다**
- 상태: **의도·형식 초안 고정, 스키마·사례 수집·실행기는 미확정**
- 관련:
  - 채팅 E2E 최소 구조 핸드오프: `10-vertical-mvp-handoff.md`
  - 런타임 job pairwise(별도 경로): `ResponseComparisonRecord` / `app/evaluation/response_comparison.py`
  - 예전 분리 하네스(이 문제집과 **다른 목적**): `app/evaluation/run_response_comparison.py`, `07-evaluation-continuation.md`

## 1. 이 문서가 답하려는 질문

**같은 고정 일반론 세트를 반복 실행할 때, 서비스(대화 노드 + 그때그때 쌓인 RAG 인덱스)가 LLM Judge 절대 점수 기준으로 전반적으로 성장하고 있는가?**

- 각 실행 시점의 **RAG 축적 상태**(공용/원고 인덱스에 무엇이 있는지)는 다를 수 있고, 그에 따라 **같은 주장에 대한 converse/feedback 응답도 달라질 수 있다.**
- 목적은 그 변화를 **절대 점수 총계·항목별 나열**로 남겨, 서비스가 나아지는지 관측하는 것.
- **목적 아님:**
  - 점수 미달 시 PR/배포를 막는 **합격선(게이트)**
  - 한 실행 안에서 baseline(무근거) vs grounded(유근거) **pairwise 승률**로 “근거를 붙이면 얼마나 나은가”만 보는 실험  
    → 그건 job 완료 시 `ResponseComparisonRecord` 등 **별도 관측 경로**에 남긴다. 이 문제집의 질문이 아니다.

### 예전 문서와의 차이 (반드시 구분)

| | 예전 서술 (`07`, 옛 `11` 초안, 설계 §일부) | **이 문제집 (확정)** |
|---|---|---|
| 질문 | 웹 근거를 붙였을 때 답이 pairwise로 얼마나 나은가 | **서비스 전반이 성장하는가** (축적·경로 개선 반영) |
| 사례 | 주장 + (종종) 미리 박힌 근거/쌍 | **일반론 문장만** |
| 생성 | 서비스 밖 baseline/grounded 프롬프트 | **`converse`/`feedback` 노드 직접** + `load_evidence_text_for_turn` (Route 없음; 세트에 phase 구분). **LangFeather 트레이싱** |
| 판정 | pairwise (baseline vs grounded) | **단일 응답 절대 점수** (구체성·자연스러움·정확성·overall 등) |
| 집계 | 승/무/패·승률 | **실행 회차별 총계 + 항목별** → 마크다운 리포트 (시계열 비교) |

## 2. 왜 별도 계획인가

채팅 E2E(#24)는 “한 바퀴가 도는지”에 가깝다.  
job 끝 pairwise와 예전 `run_response_comparison`은 **한 시점의 근거 효과**에 가깝다.

이 문제집은:

- 고정 **30~50 일반론**으로 **같은 입력**을 반복하고
- **그때의 인덱스·제품 경로**로 나온 답을 Judge가 절대 점수로 매기며
- 결과를 마크다운에 남겨 **서비스 성장**을 본다.

제품 배선과 측정 절차는 분리하되, **생성은 제품 노드를 탄다.**

## 3. 측정 단위 (합의)

### 문제집 한 줄 (입력만)

1. **사용자 일반론/주장** 한 문장(또는 짧은 단락)  
   - 예: 「RAG를 사용하면 LLM 응답의 품질이 좋아진다.」
2. **(선택 메타)** 주제 태그 — AI, FastAPI, Python, Spring, Java, 프론트엔드, CI/CD, 클라우드 등  
3. 사례에 **근거 유무·URL·prepared_evidence를 넣지 않는다.**

### 한 번 실행에서 사례당 하는 일

1. 딥다이브(또는 수업 자료) 맥락에서 해당 주장을 **실서비스 경로**로 넣음  
2. 사례에 적힌 위상(`say`→`converse` / `feedback`→`feedback`)으로 **해당 노드만** 실제 LLM 호출  
   - Route/classifier는 타지 않음. 라우팅 규칙이 선명하므로 **문제집을 converse용·feedback용으로 구분해** 작성  
   - 근거: 평가기가 `load_evidence_text_for_turn`으로 **그 시점 인덱스만** 주입 (없으면 없이)  
   - **평가 회차 중 조사 job을 만들지 않음**  
   - 실행은 **LangFeather에 트레이싱**되게 함 (`LANGFEATHER_ENABLED`; 제품과 동일 관측 스택)
3. **LLM Judge**가 그 **단일 응답**에 절대 점수 (기존 기준 재사용 가능: specificity / naturalness / accuracy / overall, 0~100)
4. 기록: 응답 본문, 점수, (가능하면) 주입된 근거 요약/출처 키, 생성·Judge 모델명, 실행 시각, 인덱스/환경 힌트, LangFeather run 상관 ID(가능하면)

### 집계·산출물

- **총계**: 사례 수, 기준별 평균·분포, 실패/스킵 수
- **항목별**: case_id, 주장, 점수, Judge 사유, (선택) 근거 유무 메모
- 파일: **마크다운** (실행마다 새 파일 또는 dated run). **합격 커트라인 없음.**
- 여러 실행의 마크다운을 나란히 보면 “서비스가 성장하는가”를 판단

### 모델

- 생성·Judge: 지금은 **DeepSeek V4 flash** (설정으로 Judge만 교체 가능하게 둘 여지)
- 임베딩: 제품과 동일 (**OpenAI**)

## 4. 문제집(30~50)에 넣을 것 / 빼 둘 것

### 넣을 것

- 엔지니어링 일반론·모범 사례·대략 수치 주장  
  도메인 예: AI/LLM/RAG, FastAPI, Python, Spring, Java, 프론트엔드, CI/CD, 클라우드 등
- 한국어 위주, 필요 시 영어·혼합 소수
- 조사 트리거가 걸릴 만한 문장 (맞장구·인사만 제외)
- **공개 웹에서 언젠가 근거를 찾을 수 있을 법한** 주장 (세트 자체에는 URL을 넣지 않음)

### 빼 둘 것

- detector precision/recall 전용 세트
- 인용 ≡ 원문 글자 일치 검사
- 배포 게이트
- shadow-only 로깅
- 사례 fixture에 baseline/grounded 쌍·미리 박힌 corpus chunk를 넣는 형태  
  (그건 예전 분리 평가용; 이 문제집과 혼동하지 말 것)

## 5. 지금 상태

- job 런타임 pairwise DB 저장: **있음** (이 문제집과 목적 다름 — 유지)
- 고정 일반론 세트 + 제품 노드 + 절대 점수 + MD 리포트: **없음**
- 예전 `tests/evaluation/agentic_rag_cases.json` + `run_response_comparison`: **서비스 분리 하네스** — 재사용은 Judge 점수 스키마·리포트 유틸 정도만 검토, 사례 형식·생성 경로는 새로 잡음

## 6. 다음에 확정할 것 (체크리스트)

- [ ] 사례 JSON 스키마 (주장 + 태그 + id 정도)
- [ ] 30~50 후보 일반론 초안 (엔지니어링 도메인 균형)
- [ ] 실행기: **현재 인덱스만** + `load_evidence_text_for_turn` → 사례 `phase`에 따라 `converse`/`feedback` 노드 직접 호출 → Judge 절대 점수 → 마크다운  
  (**확정:** 평가 중 조사 job 없음. Route 안 탐. 문제집은 say/feedback 구분 작성. **LangFeather 트레이싱**)
- [ ] LangFeather: 노드 직접 호출이어도 wrap 대상(얇은 runnable/소그래프) 확보
- [ ] 기존 pairwise runner / `ResponseComparisonRecord`와 **경계** (혼용 금지, 재사용 범위)
- [ ] 비용·재실행 규칙 (모델, 동시성, API 한도)
- [ ] Judge 프롬프트: 단일 응답 절대 채점 계약
- [ ] 평가가 읽는 인덱스/테넌트 범위 (공용 실인덱스 vs 전용) — **미확정**

## 7. 제품 경로와의 관계 (혼동 금지)

| | 채팅 제품 | job 끝 pairwise | **이 문제집** |
|---|---|---|---|
| 질문 | 조사가 돌고 다음 말에 근거가 쓰이는가 | 그 job 근거로 만든 두 답 중 어느 쪽이 나은가 | **서비스가 회차마다 성장하는가** |
| 입력 | 사용자 대화 | job 쿼리 + 수집 근거 | 고정 일반론 세트 |
| 생성 | converse/feedback | 평가용 baseline/grounded 생성 | **동일 제품 노드** |
| 판정 | 없음(사용자) | pairwise | **절대 점수** |
| 게이트 | 없음 | 없음 | 없음 |

**Route 이후 RAG**는 제품 과제다. 문제집은 그 결과물(축적·주입·응답 품질)이 **시간에 따라 나아지는지**를 밖에서 숫자로 보는 도구다.
