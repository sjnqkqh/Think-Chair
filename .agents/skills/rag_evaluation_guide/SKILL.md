---
name: rag-evaluation-guide
description: RAG 다중 청킹 파이프라인 및 DeepSeek 기반 RAGAS/LLM Judge 평가 및 성능 비교 대시보드 가이드라인
---

# RAG 다중 청킹 및 성능 평가 가이드 (rag-evaluation-guide)

이 스킬은 프로젝트 내에서 다양한 텍스트 분할(Chunking) 방식에 따른 RAG Retrieval 및 Generation 성능을 정량적으로 평가하고 채점하는 방법론을 안내합니다.

## 1. 다중 청킹 및 적재 파이프라인
* **서비스 컴포넌트**: [ChunkingService](file:///Users/jungjin/PycharmProjects/RAG-Integrated-AI/app/services/chunking.py)
* **지원 포맷**: TXT, MD, PDF (pypdf 활용)
* **청킹 전략 종류**:
  1. `RecursiveCharacterTextSplitter`: 텍스트 단위 분할 (크기, 오버랩 조절).
  2. `CharacterTextSplitter`: 고정 구분자(예: 이중 개행 `\n\n`) 분할.
  3. `MarkdownHeaderTextSplitter`: 헤더 구조(`#`, `##`, `###`) 계층 분할.
* **적재 방식**: 전략별로 Chroma DB 내에 `rag_rec_s500_o50`, `rag_md_header` 등의 고유 컬렉션명으로 분류하여 격리 저장합니다.

## 2. 평가 방법론 (LLM as Judge vs RAGAS)
RAG 성능 평가는 **DeepSeek v4-flash / V3 (deepseek-chat)** 모델을 판별관(Judge)으로 사용해 진행하며 두 가지 채점 방식을 제공합니다.

### A. 커스텀 LLM as Judge (엄격한 Grading Rubric)
* **평가 기준**:
  1. **충실성 (Faithfulness)**: 사실관계 100% 부합 여부. 주관적 추론이나 연결사가 과도하게 섞일 시 4점 이하 감점.
  2. **답변 연관성 (Answer Relevance)**: 질문 요구 요소(직업, 경력, 기술 등) 누락 및 TMI 혼입 여부 검증.
  3. **컨텍스트 정확성 (Context Precision)**: 검색된 Top-K 청크 중 노이즈 청크(무관 정보)의 비율을 수식적으로 추적하여 감점.
* **동작 방식**: 평가 지문 및 루브릭이 담긴 프롬프트를 DeepSeek에 주입해 정형화된 JSON 점수와 사유를 직접 회신받음.

### B. RAGAS (Retrieval Augmented Generation Assessment) 통합
* **평가 기준**: 학계 표준 지표인 Faithfulness, Answer Relevance, Context Precision 산출 (0~1.0 척도를 대시보드 호완을 위해 1~5점으로 환산).
* **동작 방식**: LangChain의 `ChatOpenAI`를 DeepSeek로 감싸고, `GoogleGenerativeAIEmbeddings`를 Ragas 라이브러리에 주입하여 datasets의 `evaluate` 함수를 통해 비동기로 정밀 측정.

## 3. 테스트 및 품질 무결성 검증
* **유닛 테스트**: [test_main.py](file:///Users/jungjin/PycharmProjects/RAG-Integrated-AI/test_main.py)에서 Mocking 기반으로 `/upload` 및 `/eval/run` API 동작 유효성 상시 검증.
* **골든 셋 회귀 테스트**: [test_rag_quality.py](file:///Users/jungjin/PycharmProjects/RAG-Integrated-AI/tests/test_rag_quality.py)에서 [golden_dataset.json](file:///Users/jungjin/PycharmProjects/RAG-Integrated-AI/tests/data/golden_dataset.json)의 실제 질문셋을 기반으로, RAG 응답의 평균 점수가 **4.0점 이상**인지 주기적으로 검증 (DeepSeek API Key가 등록되어 있을 때 활성화).
