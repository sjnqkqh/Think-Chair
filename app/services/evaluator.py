import asyncio
import json
import logging
from typing import List, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from kiwipiepy import Kiwi
from app.core.config import settings
from app.core.vectorstore import VectorStoreManager
from app.core.llm import LLMManager
from app.core.retry import execute_with_retry

logger = logging.getLogger(__name__)
kiwi = Kiwi()


def compute_coverage_rate(gt: str, contexts: List[str]) -> float:
    if not gt:
        return 0.0
    gt_tokens = set([t.form for t in kiwi.tokenize(gt) if t.tag.startswith("N") or t.tag.startswith("V")])
    if not gt_tokens:
        return 0.0
    context_text = " ".join(contexts)
    ctx_tokens = set([t.form for t in kiwi.tokenize(context_text) if t.tag.startswith("N") or t.tag.startswith("V")])
    matching_tokens = gt_tokens.intersection(ctx_tokens)
    return round(len(matching_tokens) / len(gt_tokens), 4)


def compute_gt_match_rate(gt: str, answer: str) -> float:
    if not gt or not answer:
        return 0.0
    gt_tokens = set([t.form for t in kiwi.tokenize(gt) if t.tag.startswith("N") or t.tag.startswith("V")])
    if not gt_tokens:
        return 0.0
    ans_tokens = set([t.form for t in kiwi.tokenize(answer) if t.tag.startswith("N") or t.tag.startswith("V")])
    matching_tokens = gt_tokens.intersection(ans_tokens)
    return round(len(matching_tokens) / len(gt_tokens), 4)


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
   • 3점 (Fair): 답변 중 1개 이상의 문장이 맥락에 명시되어 있지 않은 간접적 추론/가정에 의존하고 있음. (환각 진술 1개)
   • 2점 (Poor): 답변의 핵심 부분에 맥락과 무관하거나 맥락을 오해한 서술, 또는 외부 지식에만 기댄 설명이 명백히 섞여 있음. (환각 진술 2개 이상)
   • 1점 (Critical): 답변이 맥락의 내용과 정면으로 모순되거나 심각한 환각(Hallucination)을 보임.

2. 답변 연관성 (Answer Relevance, 1~5점) - 질문에 대한 연관도 검증
   • 5점 (Excellent): 질문의 의도를 완전히 이해하고 질문에 매우 직접적이고 적합한 문맥적 답변을 제공함.
   • 4점 (Good): 질문에 대답은 잘 하였으나, 질문과 직접적 연관이 적은 약간의 군더더기 서술(TMI)이 한 문장 정도 포함됨.
   • 3점 (Fair): 질문의 요지는 짚었으나, 답변에 질문과 관계없는 무관한 정보가 30% 이상 포함되어 집중도가 떨어짐.
   • 2점 (Poor): 질문에 대답을 하려는 목적은 보이나 질문에 대한 핵심 답변을 우회하거나 우회적인 얕은 정보만 기술함.
   • 1점 (Critical): 질문과 아예 다른 엉뚱한 답변을 하거나 답변 불가능함을 선언함.

3. 컨텍스트 정확성 (Context Precision, 1~5점) - Retriever 검색 효율 및 노이즈 검증
   • 5점 (Excellent): 검색된 모든 청크(Context)가 질문에 답변하기 위해 반드시 필요한 유효하고 가치 있는 정보로만 채워짐. 노이즈 정보(질문과 관련 없는 청크)가 전혀 없음.
   • 4점 (Good): 핵심 정보를 포함한 청크 외에, 질문과 관련성이 조금 떨어지거나 중복되는 무의미한 노이즈 청크가 1개 섞여 있음.
   • 3점 (Fair): 검색된 전체 청크 중 절반(50%) 이상이 질문과 관계없는 무관한 정보거나 중복된 정보임.
   • 2점 (Poor): 질문과 직접적으로 관련된 유의미한 청크는 1개 이하이고, 나머지 대부분의 청크가 무관한 노이즈로 가득 참.
   • 1점 (Critical): 가져온 모든 청크가 질문에 답변하는 데 아무런 도움이 되지 않음.

4. 컨텍스트 재현율 (Context Recall, 1~5점) - Retriever 검색 완전성 검증 (신규)
   • 5점 (Excellent): 정답 가이드라인(Ground Truth)에 기재된 모든 핵심 수치, 기준, 예외 조건이 검색된 맥락(Context) 내에 빠짐없이 존재함.
   • 4점 (Good): 정답 가이드라인의 주요 내용은 충족하나, 1개의 미세한 부가 조건(예: 특정 면제 조항 등)만 검색된 맥락에서 누락됨.
   • 3점 (Fair): 정답 가이드라인의 핵심 사항 중 약 30~50%에 달하는 중대 정보가 검색된 맥락 내에 존재하지 않음.
   • 2점 (Poor): 정답 가이드라인의 결론은 포함하나, 그 핵심 근거가 되는 조항이나 수치가 대부분 검색된 맥락에서 발견되지 않음.
   • 1점 (Critical): 정답 가이드라인과 관련된 정보가 검색된 맥락에 아예 존재하지 않음.

5. 답변 완결성 (Answer Completeness, 1~5점) - 생성 답변의 완성도 검증 (신규)
   • 5점 (Excellent): 정답 가이드라인(Ground Truth)의 모든 필수 정보, 구체적 수치, 기준, 예외 사항이 답변에 누락 없이 정확하게 포함됨.
   • 4점 (Good): 필수 정보는 다루었으나, 수치나 기준 표현이 다소 추상적으로 뭉뚱그려졌거나(예: '3회'를 '수차례'로 기술), 사소한 예외 하나가 기술에서 빠짐.
   • 3점 (Fair): 정답 가이드라인에서 요구하는 핵심 항목 중 1~2개가 답변에서 완전히 생략되거나 잘못 서술됨.
   • 2점 (Poor): 정답 가이드라인 필수 내용 중 50% 이상이 답변에서 누락되어 매우 불충분한 정보만 포함함.
   • 1점 (Critical): 생성된 답변과 정답 가이드라인 간 일치하는 유의미한 필수 지식이 사실상 존재하지 않음.

반드시 아래 JSON 형식으로만 응답해야 합니다. 추가적인 텍스트 없이 JSON만 반환하십시오.

[출력 JSON 포맷]
{{
  "faithfulness": {{
    "score": 5,
    "reason": "엄격한 루브릭 기준 몇 점에 해당하는지 구체적인 문장 분석 결과와 함께 사유를 작성하십시오."
  }},
  "relevance": {{
    "score": 4,
    "reason": "질문의 요지와 일치하는 대답을 하였는지 구체적인 사유를 작성하십시오."
  }},
  "precision": {{
    "score": 5,
    "reason": "검색된 N개의 청크 중 노이즈 청크가 몇 개가 존재하고, 이로 인해 검색 품질이 왜곡되었는지 구체적인 비율을 따져 작성하십시오."
  }},
  "recall": {{
    "score": 5,
    "reason": "정답 가이드라인에 서술된 주요 지식이 검색된 맥락에 정확히 나타나 있는지, 누락된 핵심 항목이 무엇인지 밝혀 작성하십시오."
  }},
  "completeness": {{
    "score": 5,
    "reason": "정답 가이드라인과 비교하여 생성 답변이 모든 조항이나 수치를 빠짐없이 커버했는지 상세 분석을 적으십시오."
  }},
  "noise_ratio": 0.0,
  "hallucination_count": 0
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

    async def evaluate_answer(
        self, question: str, ground_truth: str, context: List[str], answer: str
    ) -> Dict[str, Any]:
        formatted_context = "\n---\n".join(context)
        formatted_prompt = self.judge_prompt.format_messages(
            question=question,
            context=formatted_context,
            ground_truth=ground_truth,
            answer=answer,
        )

        coverage_rate = compute_coverage_rate(ground_truth, context)
        gt_match_rate = compute_gt_match_rate(ground_truth, answer)
        avg_chunk_length = (
            int(sum(len(c) for c in context) / len(context)) if context else 0
        )

        try:
            response = await self.judge_llm.ainvoke(formatted_prompt)
            result = json.loads(response.content)

            result["coverage_rate"] = coverage_rate
            result["gt_match_rate"] = gt_match_rate
            result["avg_chunk_length"] = avg_chunk_length

            if "noise_ratio" not in result:
                result["noise_ratio"] = 0.0
            if "hallucination_count" not in result:
                result["hallucination_count"] = 0

            return result
        except Exception as e:
            logger.error(f"Error during DeepSeek Judge evaluation: {e}")
            return {
                "faithfulness": {"score": 0, "reason": f"Evaluation error: {str(e)}"},
                "relevance": {"score": 0, "reason": f"Evaluation error: {str(e)}"},
                "precision": {"score": 0, "reason": f"Evaluation error: {str(e)}"},
                "recall": {"score": 0, "reason": f"Evaluation error: {str(e)}"},
                "completeness": {"score": 0, "reason": f"Evaluation error: {str(e)}"},
                "noise_ratio": 0.0,
                "coverage_rate": coverage_rate,
                "hallucination_count": 0,
                "gt_match_rate": gt_match_rate,
                "avg_chunk_length": avg_chunk_length,
            }

    async def evaluate_with_ragas(
        self, question: str, ground_truth: str, context: List[str], answer: str
    ) -> Dict[str, Any]:
        judge_res = await self.evaluate_answer(question, ground_truth, context, answer)

        try:
            from datasets import Dataset
            from ragas import evaluate
            from ragas.metrics import (
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            )
            import nest_asyncio
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            embeddings = GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-2",
                google_api_key=settings.GEMINI_API_KEY,
            )

            nest_asyncio.apply()

            metrics = [
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ]
            
            data = {
                "question": [question],
                "answer": [answer],
                "contexts": [context],
                "ground_truth": [ground_truth],
            }
            dataset = Dataset.from_dict(data)

            ragas_result = await asyncio.to_thread(
                execute_with_retry,
                evaluate,
                dataset=dataset,
                metrics=metrics,
                llm=self.judge_llm,
                embeddings=embeddings,
                max_retries=5,
                base_delay=2.0,
            )

            try:
                faithfulness_score = int(round(ragas_result["faithfulness"] * 5))
            except Exception:
                faithfulness_score = 0

            try:
                relevance_score = int(round(ragas_result["answer_relevancy"] * 5))
            except Exception:
                relevance_score = 0

            try:
                precision_score = int(round(ragas_result["context_precision"] * 5))
            except Exception:
                precision_score = 0

            try:
                recall_score = int(round(ragas_result["context_recall"] * 5))
            except Exception:
                recall_score = 0

            faithfulness_score = max(1, min(5, faithfulness_score)) if faithfulness_score > 0 else 1
            relevance_score = max(1, min(5, relevance_score)) if relevance_score > 0 else 1
            precision_score = max(1, min(5, precision_score)) if precision_score > 0 else 1
            recall_score = max(1, min(5, recall_score)) if recall_score > 0 else 1

            def format_ragas_reason(metric_name):
                try:
                    val = ragas_result[metric_name]
                    return f"Ragas Score: {val:.2f}/1.00 (DeepSeek Judge 판별)"
                except Exception:
                    return "N/A"

            return {
                "faithfulness": {
                    "score": faithfulness_score,
                    "reason": format_ragas_reason("faithfulness"),
                },
                "relevance": {
                    "score": relevance_score,
                    "reason": format_ragas_reason("answer_relevancy"),
                },
                "precision": {
                    "score": precision_score,
                    "reason": format_ragas_reason("context_precision"),
                },
                "recall": {
                    "score": recall_score,
                    "reason": format_ragas_reason("context_recall"),
                },
                "completeness": judge_res.get("completeness", {"score": 0, "reason": "N/A"}),
                "noise_ratio": judge_res.get("noise_ratio", 0.0),
                "coverage_rate": judge_res.get("coverage_rate", 0.0),
                "hallucination_count": judge_res.get("hallucination_count", 0),
                "gt_match_rate": judge_res.get("gt_match_rate", 0.0),
                "avg_chunk_length": judge_res.get("avg_chunk_length", 0),
            }

        except Exception as exception:
            logger.error(f"Error during Ragas evaluation: {exception}")
            logger.warning(
                "Ragas evaluation failed. Falling back to direct LLM Judge evaluation."
            )
            return judge_res

    async def run_evaluation_for_strategy(
        self,
        question: str,
        ground_truth: str,
        collection_name: str,
        top_k: int = 5,
        use_ragas: bool = False,
    ) -> Dict[str, Any]:
        store = self.vector_store_manager.get_vector_store(collection_name)
        retriever = store.as_retriever(search_kwargs={"k": top_k})
        documents = await retriever.ainvoke(question)
        contexts = [document.page_content for document in documents]

        stuff_chain = self.llm_manager.create_stuff_chain()
        answer = await stuff_chain.ainvoke(
            {"input": question, "chat_history": [], "context": documents}
        )

        if use_ragas:
            scores = await self.evaluate_with_ragas(question, ground_truth, contexts, answer)
        else:
            scores = await self.evaluate_answer(question, ground_truth, contexts, answer)

        return {"answer": answer, "contexts": contexts, "scores": scores}

