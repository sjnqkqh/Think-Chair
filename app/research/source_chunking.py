import hashlib
import re
import unicodedata
import uuid
from functools import cache

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.research.contracts import FetchedSource, ResearchSourceChunk

CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
CHUNK_SCHEMA_VERSION = "chunk-600-100-v1"


@cache
def _retrieval_text_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=[
            "\n\n",
            "\n",
            "。",
            "！",
            "？",
            ". ",
            "! ",
            "? ",
            "; ",
            "；",
            " ",
            "",
        ],
        keep_separator="end",
        add_start_index=True,
    )


def classify_text_language(text: str) -> str:
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    letters = hangul + latin
    if not letters:
        return "und"
    if hangul / letters >= 0.2 and latin / letters >= 0.2:
        return "mixed"
    return "ko" if hangul > latin else "en"


def _retrieval_chunk_id(
    source_id: uuid.UUID,
    ordinal: int,
    text: str,
    chunk_schema_version: str,
) -> str:
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    identity = f"{source_id}:{chunk_schema_version}:{ordinal}:{content_hash}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def split_source_for_retrieval(
    source: FetchedSource,
    source_id: uuid.UUID,
    *,
    chunk_schema_version: str = CHUNK_SCHEMA_VERSION,
) -> list[ResearchSourceChunk]:
    pieces = [("page", source.canonical_url, source.text)]
    pieces.extend(
        (section.kind, section.permalink, section.text) for section in source.sections
    )

    chunks: list[ResearchSourceChunk] = []
    for section_kind, source_url, text in pieces:
        normalized = unicodedata.normalize("NFC", text).replace("\r\n", "\n").strip()
        if not normalized:
            continue
        for document in _retrieval_text_splitter().create_documents([normalized]):
            ordinal = len(chunks)
            chunks.append(
                ResearchSourceChunk(
                    id=_retrieval_chunk_id(
                        source_id,
                        ordinal,
                        document.page_content,
                        chunk_schema_version,
                    ),
                    source_id=source_id,
                    ordinal=ordinal,
                    text=document.page_content,
                    start_index=document.metadata["start_index"],
                    source_url=source_url,
                    section_kind=section_kind,
                    language=classify_text_language(document.page_content),
                    chunk_schema_version=chunk_schema_version,
                )
            )
    return chunks
