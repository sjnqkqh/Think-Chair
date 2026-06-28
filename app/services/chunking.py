import io
from typing import List, Dict, Any
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    CharacterTextSplitter,
    MarkdownHeaderTextSplitter,
)


class ChunkingService:
    @staticmethod
    def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
        ext = filename.split(".")[-1].lower()
        if ext == "pdf":
            pdf_file = io.BytesIO(file_bytes)
            reader = PdfReader(pdf_file)
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts)
        elif ext in ["txt", "md", "json"]:
            return file_bytes.decode("utf-8", errors="ignore")
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    @staticmethod
    def split_document(
        text: str, strategy: Dict[str, Any], filename: str
    ) -> List[Document]:
        strategy_name = strategy.get("name", "recursive")
        metadata = {"source": filename}

        if strategy_name == "recursive":
            chunk_size = strategy.get("chunk_size", 500)
            chunk_overlap = strategy.get("chunk_overlap", 50)
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size, chunk_overlap=chunk_overlap, length_function=len
            )
            docs = splitter.create_documents([text], metadatas=[metadata])
            for i, doc in enumerate(docs):
                doc.metadata["chunk_index"] = i
                doc.metadata["strategy"] = f"recursive_{chunk_size}_{chunk_overlap}"
            return docs

        elif strategy_name == "character":
            separator = strategy.get("separator", "\n\n")
            chunk_size = strategy.get("chunk_size", 500)
            chunk_overlap = strategy.get("chunk_overlap", 50)
            splitter = CharacterTextSplitter(
                separator=separator, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
            docs = splitter.create_documents([text], metadatas=[metadata])
            for i, doc in enumerate(docs):
                doc.metadata["chunk_index"] = i
                doc.metadata["strategy"] = f"character_{chunk_size}_{chunk_overlap}"
            return docs

        elif strategy_name == "markdown_header":
            headers_to_split_on = [
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
            ]
            splitter = MarkdownHeaderTextSplitter(
                headers_to_split_on=headers_to_split_on
            )
            docs = splitter.split_text(text)
            for i, doc in enumerate(docs):
                doc.metadata.update(metadata)
                doc.metadata["chunk_index"] = i
                doc.metadata["strategy"] = "markdown_header"
            return docs

        else:
            splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
            docs = splitter.create_documents([text], metadatas=[metadata])
            for i, doc in enumerate(docs):
                doc.metadata["chunk_index"] = i
                doc.metadata["strategy"] = "default"
            return docs

    @staticmethod
    def get_collection_name_for_strategy(strategy: Dict[str, Any]) -> str:
        strategy_name = strategy.get("name", "recursive")
        if strategy_name == "recursive":
            return f"rag_rec_s{strategy.get('chunk_size', 500)}_o{strategy.get('chunk_overlap', 50)}"
        elif strategy_name == "character":
            return f"rag_char_s{strategy.get('chunk_size', 500)}_o{strategy.get('chunk_overlap', 50)}"
        elif strategy_name == "markdown_header":
            return "rag_md_header"
        return "rag_default"
