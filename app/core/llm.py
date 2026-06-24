import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains import create_retrieval_chain
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMManager:
    def __init__(self):
        api_key = settings.DEEPSEEK_API_KEY
        if api_key and api_key != "your_deepseek_api_key_here":
            logger.info(f"Initializing ChatOpenAI with DeepSeek model: {settings.DEEPSEEK_MODEL}")
            self.llm = ChatOpenAI(
                openai_api_key=api_key,
                openai_api_base=settings.DEEPSEEK_API_BASE,
                model_name=settings.DEEPSEEK_MODEL,
                temperature=0.3
            )
        else:
            logger.warning("DEEPSEEK_API_KEY is not set. Falling back to ChatGoogleGenerativeAI (Gemini).")
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=settings.GEMINI_API_KEY
            )
        
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", """당신은 제공된 문서(Context)를 바탕으로 질문에 답하는 전문 AI 어시스턴트입니다.

[규칙 및 지침]
1. 반드시 제공된 문서(Context)의 사실에만 기반하여 질문에 답하십시오. 문서에 존재하지 않는 사실을 임의로 가정하거나 유추하여 답변을 왜곡해서는 안 됩니다.
2. 만약 제공된 문서(Context) 내에서 질문에 대한 답을 찾을 수 없거나 정보가 부족한 경우, 다른 임의의 답변을 지어내지 말고 정확히 다음 문장만을 반환하십시오: "제공된 문서에서 관련 내용을 찾을 수 없습니다."
3. 문서에 언급된 수치나 마감일, 규칙 등은 왜곡 없이 정확하게 전달하십시오.
4. 정중하고 객관적인 톤앤매너(존댓말)를 유지하십시오.
5. 최종 답변은 반드시 한국어로 작성하십시오.

[제공된 문서 (Context)]
{context}"""),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}")
        ])


    def create_rag_chain(self, retriever):
        question_answer_chain = create_stuff_documents_chain(self.llm, self.prompt_template)
        return create_retrieval_chain(retriever, question_answer_chain)

    def create_stuff_chain(self):
        return create_stuff_documents_chain(self.llm, self.prompt_template)

