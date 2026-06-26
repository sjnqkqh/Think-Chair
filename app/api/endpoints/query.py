from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
import json
from app.schemas.rag import QueryRequest, QueryResponse
from app.services.rag import RagService

router = APIRouter()
_rag_service_instance = None


def get_rag_service() -> RagService:
    global _rag_service_instance
    if _rag_service_instance is None:
        try:
            _rag_service_instance = RagService()
        except Exception as exception:
            raise HTTPException(
                status_code=500, detail=f"Failed to initialize RAG Service: {str(exception)}"
            )
    return _rag_service_instance


@router.post("/query", response_model=QueryResponse, summary="RAG 질의 요청")
async def query_rag(
    request: QueryRequest,
    rag_service: RagService = Depends(get_rag_service)
):
    try:
        result = rag_service.query(request.question, request.session_id, request.top_k)
        return QueryResponse(
            answer=result["answer"],
            contexts=result["contexts"],
            metadatas=result["metadatas"],
        )
    except Exception as exception:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(exception)}")


@router.post("/query/stream", summary="RAG 질의 요청 (스트리밍)")
async def query_rag_stream(
    request: QueryRequest,
    rag_service: RagService = Depends(get_rag_service)
):
    try:
        response_stream, documents, metadatas = rag_service.query_stream(
            request.question, request.session_id, request.top_k
        )
    except Exception as exception:
        raise HTTPException(status_code=500, detail=f"Streaming query failed: {str(exception)}")

    def sse_generator():
        metadata = {"contexts": documents, "metadatas": metadatas}
        yield f"event: metadata\ndata: {json.dumps(metadata, ensure_ascii=False)}\n\n"

        for chunk in response_stream:
            if chunk.text:
                yield f"data: {chunk.text}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
