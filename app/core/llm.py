from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains import create_retrieval_chain
from app.core.config import settings

class LLMManager:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.GEMINI_API_KEY
        )
        
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", """You are a professional operations support AI assistant helping students (crews) of Kakao Tech Bootcamp 4th class.
Your primary role is to answer questions strictly based on the provided [Education Rules and Regulations Document] (Context).

[Rules & Guidelines]
1. You must answer the student's question based strictly on the facts provided in the [Education Rules and Regulations Document] (Context). Do not assume, extrapolate, or generate any information that is not explicitly stated in the context.
2. If you cannot find the answer in the provided context, or if the information is insufficient, do not make up an answer. Instead, respond with exactly: "제공된 규정 문서에서 관련 내용을 찾을 수 없습니다. 운영팀(헬퍼라이언)에 문의하시기 바랍니다."
3. When referencing specific numbers or deadlines (e.g., "3 days prior", "80% or more", "3 accumulated warnings"), state them clearly and accurately.
4. Maintain a polite, professional, and friendly tone using honorifics (존댓말).
5. IMPORTANT: You must write the final response in Korean, regardless of the prompt language.

[Education Rules and Regulations Document (Context)]
{context}"""),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}")
        ])

    def create_rag_chain(self, retriever):
        question_answer_chain = create_stuff_documents_chain(self.llm, self.prompt_template)
        return create_retrieval_chain(retriever, question_answer_chain)

    def create_stuff_chain(self):
        return create_stuff_documents_chain(self.llm, self.prompt_template)
