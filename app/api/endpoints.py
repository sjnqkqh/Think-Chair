import os
import json
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse, HTMLResponse
from app.schemas.rag import QueryRequest, QueryResponse, IndexResponse
from app.services.rag import RagService
from app.core.config import settings

router = APIRouter()
_service = None


def get_rag_service() -> RagService:
    global _service
    if _service is None:
        try:
            _service = RagService()
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to initialize RAG Service: {str(e)}"
            )
    return _service


@router.get("/")
async def root():
    return {
        "service": "KTB4 Rules RAG Service API",
        "status": "online",
        "documentation": "/docs",
    }


@router.post("/index", response_model=IndexResponse, summary="규칙 문서 인덱싱 수행")
async def run_indexing(service: RagService = Depends(get_rag_service)):
    try:
        count = service.index_documents()
        return IndexResponse(status="success", indexed_count=count)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.post("/query", response_model=QueryResponse, summary="RAG 질의 요청")
async def query_rag(req: QueryRequest, service: RagService = Depends(get_rag_service)):
    try:
        result = service.query(req.question, req.session_id, req.top_k)
        return QueryResponse(
            answer=result["answer"],
            contexts=result["contexts"],
            metadatas=result["metadatas"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.post("/query/stream", summary="RAG 질의 요청 (스트리밍)")
async def query_rag_stream(
    req: QueryRequest, service: RagService = Depends(get_rag_service)
):
    try:
        response_stream, documents, metadatas = service.query_stream(
            req.question, req.session_id, req.top_k
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Streaming query failed: {str(e)}")

    def sse_generator():
        meta = {"contexts": documents, "metadatas": metadatas}
        yield f"event: metadata\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"

        for chunk in response_stream:
            if chunk.text:
                yield f"data: {chunk.text}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@router.get("/chat", response_class=HTMLResponse, summary="RAG 웹 채팅 화면")
async def chat_ui():
    template_path = os.path.join(settings.BASE_DIR, "app", "templates", "chat.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Chat HTML template not found")

    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    return HTMLResponse(content=html_content)
