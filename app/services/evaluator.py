import json
import logging
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.core.config import settings
from app.core.vectorstore import VectorStoreManager
from app.core.llm import LLMManager
from app.core.retry import execute_with_retry

logger = logging.getLogger(__name__)


class EvaluatorService:
    def __init__(self):
        self.vector_store_manager = VectorStoreManager()
        self.llm_manager = LLMManager()

        # Initialize DeepSeek Judge LLM
        # Fall back to Gemini if API key is not set, to avoid startup failure
        api_key = settings.DEEPSEEK_API_KEY
        if not api_key or api_key == "your_deepseek_api_key_here":
            logger.warning(
                "DEEPSEEK_API_KEY is not set. DeepSeek Judge will fail upon calling. Using Gemini as fallback."
            )
            self.judge_llm = self.llm_manager.llm
        else:
            self.judge_llm = ChatOpenAI(
                openai_api_key=api_key,
                openai_api_base=settings.DEEPSEEK_API_BASE,
                model_name=settings.DEEPSEEK_MODEL,
                temperature=0.0,
                model_kwargs={"response_format": {"type": "json_object"}},
            )

        self.judge_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """당신은 RAG(Retrieval-Augmented Generation) 시스템의 답변 및 검색 품질을 평가하는 전문 평가관입니다.
제공된 입력 정보를 바탕으로 생성된 답변과 검색된 맥락의 정밀성을 꼼꼼하게 분석하고 엄격한 루브릭(Rubric)에 따라 점수와 사유를 부여해 주십시오.
평가는 자비 없이 엄격하게 진행되어야 하며, 기준에서 미세하게 벗어날 경우 반드시 감점해야 변별력이 생깁니다.

[평가 지표 및 엄격한 채점 루브릭]

1. 충실성 (Faithfulness, 1~5점) - 생성 답변의 사실성 검증
   • 5점 (Excellent): 답변의 모든 문장과 수치, 사실관계가 제공된 맥락(Context)과 100% 완벽하게 일치함. 추론이나 상상, 외부 지식이 전혀 섞이지 않음.
   • 4점 (Good): 답변이 맥락의 사실에 기반하나, 질문과의 어색한 흐름을 풀기 위해 맥락에 없는 매우 사소한 표현(연결사 등)을 덧붙임. 사실 왜곡은 없음.
   • 3점 (Fair): 답변 중 1개 이상의 문장이 맥락에 명시되어 있지 않은 간접적 추론/가정에 의존하고 있음.
   • 2점 (Poor): 답변의 핵심 부분에 맥락과 무관하거나 맥락을 오해한 서술, 또는 외부 지식에만 기댄 설명이 명백히 섞여 있음.
   • 1점 (Critical): 답변이 맥락의 내용과 정면으로 모순되거나 심각한 환각(Hallucination)을 보임.

2. 답변 연관성 (Answer Relevance, 1~5점) - 질문에 대한 완결성 검증
   • 5점 (Excellent): 질문이 요구하는 모든 핵심 정보(예: 직업, 경력 수치, 주요 기술군 등)에 대해 구체적이고 누락 없이 명확한 최종 대답을 완료함.
   • 4점 (Good): 질문에 대답은 완료하였으나, 수치나 세부 명사 등이 다소 모호하게 뭉뚱그려졌거나(예: '3년 경력' 대신 '수년간의 경력') 질문과 무관한 불필요한 사족(TMI)이 한 문장 정도 포함됨.
   • 3점 (Fair): 질문이 요구한 핵심 조건이나 질문 사항 중 일부(약 50%)가 누락되어 반쪽짜리 답변에 머무름.
   • 2점 (Poor): 질문의 의도를 제대로 충족하지 못하고 주변부를 맴도는 무의미한 서술이 주를 이룸.
   • 1점 (Critical): 질문과 아예 다른 엉뚱한 답변을 하거나 답변 불가능함을 선언함.

3. 컨텍스트 정확성 (Context Precision, 1~5점) - Retriever 검색 효율 및 노이즈 검증
   • 5점 (Excellent): 검색된 모든 청크(Context)가 질문에 답변하기 위해 반드시 필요한 유효하고 가치 있는 정보로만 채워짐. 노이즈 정보(질문과 관련 없는 청크)가 전혀 없음.
   • 4점 (Good): 핵심 정보를 포함한 청크 외에, 질문과 관련성이 조금 떨어지거나 중복되는 무의미한 노이즈 청크가 1개 섞여 있음.
   • 3점 (Fair): 검색된 전체 청크 중 절반(50%) 이상이 질문과 관계없는 무관한 정보거나 중복된 정보임. (검색 효율 저하)
   • 2점 (Poor): 질문과 직접적으로 관련된 유의미한 청크는 1개 이하이고, 나머지 대부분의 청크가 무관한 노이즈로 가득 참.
   • 1.점 (Critical): 가져온 모든 청크가 질문에 답변하는 데 아무런 도움이 되지 않음.

반드시 아래 JSON 형식으로만 응답해야 합니다. 추가적인 텍스트 없이 JSON만 반환하십시오.

[출력 JSON 포맷]
{{
  "faithfulness": {{
    "score": 5,
    "reason": "엄격한 루브릭 기준 몇 점에 해당하는지 구체적인 문장 분석 결과와 함께 사유를 작성하십시오."
  }},
  "relevance": {{
    "score": 4,
    "reason": "질문에서 요구한 항목 중 무엇이 들어갔고 무엇이 모호하거나 빠졌는지 구체적 사유를 작성하십시오."
  }},
  "precision": {{
    "score": 5,
    "reason": "검색된 N개의 청크 중 노이즈 청크가 몇 개가 존재하고, 이로 인해 검색 품질이 왜곡되었는지 구체적인 비율을 따져 작성하십시오."
  }}
}}""",
                ),
                (
                    "human",
                    """[입력 정보]
- 질문 (Question): {question}
- 제공된 맥락 (Context): {context}
- 정답 가이드라인 (Ground Truth): {ground_truth}
- 생성된 답변 (Generated Answer): {answer}""",
                ),
            ]
        )

    def evaluate_answer(
        self, question: str, ground_truth: str, context: List[str], answer: str
    ) -> Dict[str, Any]:
        formatted_context = "\n---\n".join(context)
        formatted_prompt = self.judge_prompt.format_messages(
            question=question,
            context=formatted_context,
            ground_truth=ground_truth,
            answer=answer,
        )

        try:
            response = self.judge_llm.invoke(formatted_prompt)
            result = json.loads(response.content)
            return result
        except Exception as e:
            logger.error(f"Error during DeepSeek Judge evaluation: {e}")
            return {
                "faithfulness": {"score": 0, "reason": f"Evaluation error: {str(e)}"},
                "relevance": {"score": 0, "reason": f"Evaluation error: {str(e)}"},
                "precision": {"score": 0, "reason": f"Evaluation error: {str(e)}"},
            }

    def evaluate_with_ragas(
        self, question: str, ground_truth: str, context: List[str], answer: str
    ) -> Dict[str, Any]:
        # Avoid importing at module level to keep startup fast
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevance, context_precision
        import nest_asyncio

        # Create dataset for Ragas evaluation
        data = {
            "question": [question],
            "answer": [answer],
            "contexts": [context],
            "ground_truth": [ground_truth],
        }
        dataset = Dataset.from_dict(data)

        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            embeddings = GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-2",
                google_api_key=settings.GEMINI_API_KEY,
            )

            # Apply nest_asyncio to prevent asyncio event loop conflicts
            nest_asyncio.apply()

            metrics = [faithfulness, answer_relevance, context_precision]
            ragas_result = execute_with_retry(
                evaluate,
                dataset=dataset,
                metrics=metrics,
                llm=self.judge_llm,
                embeddings=embeddings,
                max_retries=5,
                base_delay=2.0,
            )

            # Scale Ragas scores from [0, 1] to [1, 5] for dashboard compatibility
            faithfulness_score = int(round(ragas_result.get("faithfulness", 0.0) * 5))
            relevance_score = int(round(ragas_result.get("answer_relevance", 0.0) * 5))
            precision_score = int(round(ragas_result.get("context_precision", 0.0) * 5))

            # Clamp to [1, 5]
            faithfulness_score = max(1, min(5, faithfulness_score))
            relevance_score = max(1, min(5, relevance_score))
            precision_score = max(1, min(5, precision_score))

            return {
                "faithfulness": {
                    "score": faithfulness_score,
                    "reason": f"Ragas Score: {ragas_result.get('faithfulness', 0.0):.2f}/1.00 (DeepSeek Judge 판별)",
                },
                "relevance": {
                    "score": relevance_score,
                    "reason": f"Ragas Score: {ragas_result.get('answer_relevance', 0.0):.2f}/1.00 (DeepSeek Judge 판별)",
                },
                "precision": {
                    "score": precision_score,
                    "reason": f"Ragas Score: {ragas_result.get('context_precision', 0.0):.2f}/1.00 (DeepSeek Judge 판별)",
                },
            }
        except Exception as exception:
            logger.error(f"Error during Ragas evaluation: {exception}")
            logger.warning(
                "Ragas evaluation failed. Falling back to direct LLM Judge evaluation."
            )
            return self.evaluate_answer(question, ground_truth, context, answer)

    def run_evaluation_for_strategy(
        self,
        question: str,
        ground_truth: str,
        collection_name: str,
        top_k: int = 5,
        use_ragas: bool = False,
    ) -> Dict[str, Any]:
        # 1. 특정 컬렉션에서 Context 검색
        store = self.vector_store_manager.get_vector_store(collection_name)
        retriever = store.as_retriever(search_kwargs={"k": top_k})
        documents = retriever.invoke(question)
        contexts = [document.page_content for document in documents]

        # 2. 답변 생성
        stuff_chain = self.llm_manager.create_stuff_chain()
        answer = stuff_chain.invoke(
            {"input": question, "chat_history": [], "context": documents}
        )

        # 3. 평가 수행
        if use_ragas:
            scores = self.evaluate_with_ragas(question, ground_truth, contexts, answer)
        else:
            scores = self.evaluate_answer(question, ground_truth, contexts, answer)

        return {"answer": answer, "contexts": contexts, "scores": scores}
