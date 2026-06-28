import logging

from kiwipiepy import Kiwi
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, AIMessage
from langsmith import traceable

from app.core.llm import LLMManager
from app.core.vectorstore import VectorStoreManager
from app.core.retry import execute_with_retry

# Initialize Kiwi morpheme analyzer once at module level
kiwi = Kiwi()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("google_genai._api_client").setLevel(logging.WARNING)


class ChunkWrapper:
    def __init__(self, text: str):
        self.text = text


class RagService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RagService, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.vector_store_manager = VectorStoreManager()
        self.llm_manager = LLMManager()
        self.sessions: dict[str, list] = {}

        try:
            self.init_bm25_retriever()
        except Exception as e:
            logger.warning(f"Error initializing BM25 retriever: {e}")
        self._initialized = True


    @staticmethod
    def kiwi_tokenize(text: str) -> list[str]:
        return [
            token.form
            for token in kiwi.tokenize(text)
            if token.tag.startswith("N") or token.tag.startswith("V")
        ]

    def init_bm25_retriever(self) -> None:
        try:
            all_data = self.vector_store_manager.vector_store.get()
            documents = []
            if all_data and "documents" in all_data and all_data["documents"]:
                for doc_text, metadata, doc_id in zip(
                    all_data["documents"], all_data["metadatas"], all_data["ids"]
                ):
                    documents.append(
                        Document(page_content=doc_text, metadata=metadata, id=doc_id)
                    )

            if documents:
                logger.info(
                    f"Initializing BM25Retriever with {len(documents)} documents..."
                )
                self.bm25_retriever = BM25Retriever.from_documents(
                    documents=documents, preprocess_func=self.kiwi_tokenize
                )
            else:
                logger.warning(
                    "No documents found in Chroma DB. BM25Retriever initialization skipped."
                )
                self.bm25_retriever = None
        except Exception as e:
            logger.error(f"Error during BM25Retriever initialization: {e}")
            self.bm25_retriever = None

    def get_ensemble_retriever(self, top_k: int):
        vector_retriever = self.vector_store_manager.vector_store.as_retriever(
            search_kwargs={"k": top_k}
        )

        if hasattr(self, "bm25_retriever") and self.bm25_retriever is not None:
            self.bm25_retriever.k = top_k
            return EnsembleRetriever(
                retrievers=[self.bm25_retriever, vector_retriever], weights=[0.3, 0.7]
            )
        return vector_retriever

    def get_session_history(self, session_id: str) -> list:
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        return self.sessions[session_id]

    @traceable(name="RagService.query", run_type="chain")
    def query(self, question: str, session_id: str, top_k: int = 5) -> dict:
        retriever = self.get_ensemble_retriever(top_k)

        logger.info("=== RAG Database Query Access ===")
        logger.info(f"Session ID: {session_id}")
        logger.info(f"Question: {question}")

        docs = execute_with_retry(retriever.invoke, question, max_retries=3, base_delay=2.0)

        logger.info(f"RAG DB Result (Found {len(docs)} documents):")
        for idx, doc in enumerate(docs):
            logger.info(
                f"  [{idx + 1}] ID: {doc.metadata.get('id')} | Content: {doc.page_content[:150]}..."
            )

        history = self.get_session_history(session_id)

        formatted_messages = self.llm_manager.prompt_template.format_messages(
            context=docs, chat_history=history, input=question
        )

        logger.info("=== Formatted Final Prompt to LLM ===")
        for idx, msg in enumerate(formatted_messages):
            logger.info(f"  [{idx + 1}] {msg.type.upper()}: {msg.content}")
        logger.info("=====================================")

        stuff_chain = self.llm_manager.create_stuff_chain()
        answer = execute_with_retry(
            stuff_chain.invoke,
            {"input": question, "chat_history": history, "context": docs},
            max_retries=3,
            base_delay=2.0,
        )

        history.append(HumanMessage(content=question))
        history.append(AIMessage(content=answer))
        self.sessions[session_id] = history[-10:]

        contexts = [doc.page_content for doc in docs]
        metadatas = [doc.metadata for doc in docs]

        return {"answer": answer, "contexts": contexts, "metadatas": metadatas}

    @traceable(name="RagService.query_stream", run_type="chain")
    def query_stream(self, question: str, session_id: str, top_k: int = 5):
        retriever = self.get_ensemble_retriever(top_k)

        logger.info("=== RAG Database Query Stream Access ===")
        logger.info(f"Session ID: {session_id}")
        logger.info(f"Question: {question}")

        docs = execute_with_retry(retriever.invoke, question, max_retries=3, base_delay=2.0)

        logger.info(f"RAG DB Result (Found {len(docs)} documents):")
        for idx, doc in enumerate(docs):
            logger.info(
                f"  [{idx + 1}] ID: {doc.metadata.get('id')} | Content: {doc.page_content[:150]}..."
            )

        history = self.get_session_history(session_id)

        formatted_messages = self.llm_manager.prompt_template.format_messages(
            context=docs, chat_history=history, input=question
        )

        logger.info("=== Formatted Final Prompt to LLM ===")
        for idx, msg in enumerate(formatted_messages):
            logger.info(f"  [{idx + 1}] {msg.type.upper()}: {msg.content}")
        logger.info("=====================================")

        contexts = [doc.page_content for doc in docs]
        metadatas = [doc.metadata for doc in docs]

        stuff_chain = self.llm_manager.create_stuff_chain()

        def response_generator():
            accumulated_answer = ""
            for chunk in stuff_chain.stream(
                {"context": docs, "input": question, "chat_history": history}
            ):
                accumulated_answer += chunk
                yield ChunkWrapper(chunk)

            history.append(HumanMessage(content=question))
            history.append(AIMessage(content=accumulated_answer))
            self.sessions[session_id] = history[-10:]

        return response_generator(), contexts, metadatas
