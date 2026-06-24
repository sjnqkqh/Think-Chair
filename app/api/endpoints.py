import os
import json
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.schemas.rag import QueryRequest, QueryResponse, IndexResponse, UploadResponse, EvalRequest, EvalResponse, StrategyEvalResult
from app.services.rag import RagService
from app.services.chunking import ChunkingService
from app.services.evaluator import EvaluatorService
from app.core.config import settings
from app.core.vectorstore import VectorStoreManager
from app.core.database import get_db
from app.models.history import UploadHistory, EvalHistory, EvalResult

router = APIRouter()
_service = None
_evaluator = None


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


def get_evaluator_service() -> EvaluatorService:
    global _evaluator
    if _evaluator is None:
        try:
            _evaluator = EvaluatorService()
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to initialize Evaluator Service: {str(e)}"
            )
    return _evaluator


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


@router.post("/upload", response_model=UploadResponse, summary="RAG 문서 업로드 및 다중 청킹 저장")
async def upload_document(
    file: UploadFile = File(...),
    strategies: str = Form(..., description="JSON format chunking strategies list"),
    db: Session = Depends(get_db)
):
    try:
        content = await file.read()
        filename = file.filename
        text = ChunkingService.extract_text_from_file(content, filename)
        
        try:
            strategy_list = json.loads(strategies)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON format for 'strategies'")
            
        vector_manager = VectorStoreManager()
        strategies_applied = []
        chunks_count = {}
        
        for strategy in strategy_list:
            docs = ChunkingService.split_document(text, strategy, filename)
            coll_name = ChunkingService.get_collection_name_for_strategy(strategy)
            
            doc_ids = [f"{filename}_{coll_name}_{i}" for i in range(len(docs))]
            vector_manager.delete_existing_documents(doc_ids, collection_name=coll_name)
            vector_manager.add_documents_batch(docs, doc_ids, collection_name=coll_name)
            
            strategies_applied.append(coll_name)
            chunks_count[coll_name] = len(docs)
            
        # Record upload history to database
        db_upload = UploadHistory(
            filename=filename,
            strategies_applied=json.dumps(strategies_applied),
            chunks_count=json.dumps(chunks_count)
        )
        db.add(db_upload)
        db.commit()
        db.refresh(db_upload)
        
        return UploadResponse(
            status="success",
            filename=filename,
            strategies_applied=strategies_applied,
            chunks_count=chunks_count
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/eval/run", response_model=EvalResponse, summary="RAG 다중 청킹 성능 평가")
async def run_evaluation(
    req: EvalRequest,
    evaluator: EvaluatorService = Depends(get_evaluator_service),
    db: Session = Depends(get_db)
):
    try:
        # 1. Record basic evaluation request info
        db_eval = EvalHistory(
            question=req.question,
            ground_truth=req.ground_truth
        )
        db.add(db_eval)
        db.commit()
        db.refresh(db_eval)
        
        results = []
        for strategy in req.strategies:
            coll_name = ChunkingService.get_collection_name_for_strategy(strategy)
            
            eval_result = evaluator.run_eval_for_strategy(
                question=req.question,
                ground_truth=req.ground_truth,
                collection_name=coll_name,
                top_k=req.top_k,
                use_ragas=req.use_ragas
            )

            strategy_str = f"{strategy.get('name')}"
            if strategy.get('name') in ['recursive', 'character']:
                strategy_str += f" (s={strategy.get('chunk_size')}, o={strategy.get('chunk_overlap')})"
                
            scores = eval_result["scores"]
            
            # 2. Record detailed evaluation result to database
            db_result = EvalResult(
                eval_history_id=db_eval.id,
                strategy=strategy_str,
                collection_name=coll_name,
                answer=eval_result["answer"],
                contexts=json.dumps(eval_result["contexts"]),
                faithfulness_score=scores.get("faithfulness", {}).get("score", 0),
                faithfulness_reason=scores.get("faithfulness", {}).get("reason", ""),
                relevance_score=scores.get("relevance", {}).get("score", 0),
                relevance_reason=scores.get("relevance", {}).get("reason", ""),
                precision_score=scores.get("precision", {}).get("score", 0),
                precision_reason=scores.get("precision", {}).get("reason", "")
            )
            db.add(db_result)
            
            results.append(StrategyEvalResult(
                strategy=strategy_str,
                collection_name=coll_name,
                answer=eval_result["answer"],
                contexts=eval_result["contexts"],
                scores=scores
            ))
            
        db.commit()
            
        return EvalResponse(
            question=req.question,
            ground_truth=req.ground_truth,
            results=results
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.get("/history/uploads", summary="업로드 이력 조회")
async def get_upload_history(db: Session = Depends(get_db)):
    histories = db.query(UploadHistory).order_by(UploadHistory.id.desc()).all()
    return [{
        "id": h.id,
        "filename": h.filename,
        "strategies_applied": json.loads(h.strategies_applied),
        "chunks_count": json.loads(h.chunks_count),
        "created_at": h.created_at.isoformat()
    } for h in histories]


@router.get("/history/evals", summary="RAG 성능 평가 이력 조회")
async def get_eval_history(db: Session = Depends(get_db)):
    histories = db.query(EvalHistory).order_by(EvalHistory.id.desc()).all()
    results = []
    for h in histories:
        eval_res = []
        for r in h.results:
            eval_res.append({
                "strategy": r.strategy,
                "collection_name": r.collection_name,
                "answer": r.answer,
                "contexts": json.loads(r.contexts),
                "scores": {
                    "faithfulness": {"score": r.faithfulness_score, "reason": r.faithfulness_reason},
                    "relevance": {"score": r.relevance_score, "reason": r.relevance_reason},
                    "precision": {"score": r.precision_score, "reason": r.precision_reason}
                }
            })
        results.append({
            "id": h.id,
            "question": h.question,
            "ground_truth": h.ground_truth,
            "created_at": h.created_at.isoformat(),
            "results": eval_res
        })
    return results


@router.get("/chat", response_class=HTMLResponse, summary="RAG 웹 채팅 화면")
async def chat_ui():
    template_path = os.path.join(settings.BASE_DIR, "app", "templates", "chat.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Chat HTML template not found")

    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    return HTMLResponse(content=html_content)

