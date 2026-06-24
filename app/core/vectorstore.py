import os
import chromadb
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document
from app.core.config import settings


class VectorStoreManager:
    def __init__(self):
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-2", google_api_key=settings.GEMINI_API_KEY
        )

        if settings.CHROMA_MODE == "docker":
            print(
                f"Connecting to Chroma DB server (Docker) at http://{settings.CHROMA_HOST}:{settings.CHROMA_PORT}..."
            )
            self.chroma_client = chromadb.HttpClient(
                host=settings.CHROMA_HOST, port=settings.CHROMA_PORT
            )
            self.vector_store = Chroma(
                client=self.chroma_client,
                collection_name="camp_rules",
                embedding_function=self.embeddings,
            )
        else:
            print(
                f"Initializing local SQLite-based persistent Chroma DB client at: {settings.CHROMA_DB_PATH}..."
            )
            self.vector_store = Chroma(
                persist_directory=settings.CHROMA_DB_PATH,
                collection_name="camp_rules",
                embedding_function=self.embeddings,
            )

    def delete_existing_documents(self, ids: list[str]) -> None:
        try:
            existing_count = self.vector_store._collection.count()
            if existing_count > 0:
                print(
                    f"Clearing {existing_count} existing items from the collection..."
                )
                self.vector_store._collection.delete(ids=ids)
        except Exception as e:
            print(f"Warning during clearing collection: {e}")

    def add_documents_batch(
        self, documents: list[Document], ids: list[str], batch_size: int = 20
    ) -> None:
        total = len(ids)
        for i in range(0, total, batch_size):
            batch_docs = documents[i : i + batch_size]
            print(f"Adding batch {i//batch_size + 1}... ({i}/{total})")
            self.vector_store.add_documents(batch_docs)
