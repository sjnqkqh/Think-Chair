from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
import json
from sqlalchemy.orm import Session

from app.schemas.rag import UploadResponse
from app.services.chunking import ChunkingService
from app.core.vectorstore import VectorStoreManager
from app.core.database import get_database_session
from app.models.history import UploadHistory

router = APIRouter()


def process_upload_task(
    history_id: int, file_bytes: bytes, filename: str, strategy_list: list
) -> None:
    database_session = next(get_database_session())
    try:
        text = ChunkingService.extract_text_from_file(file_bytes, filename)
        vector_manager = VectorStoreManager()
        strategies_applied = []
        chunks_count = {}

        for strategy in strategy_list:
            documents = ChunkingService.split_document(text, strategy, filename)
            collection_name = ChunkingService.get_collection_name_for_strategy(strategy)

            document_ids = [f"{filename}_{collection_name}_{i}" for i in range(len(documents))]
            vector_manager.delete_existing_documents(document_ids, collection_name=collection_name)
            vector_manager.add_documents_batch(documents, document_ids, collection_name=collection_name)

            strategies_applied.append(collection_name)
            chunks_count[collection_name] = len(documents)

        upload_history_record = database_session.query(UploadHistory).filter(UploadHistory.id == history_id).first()
        if upload_history_record:
            upload_history_record.status = "completed"
            upload_history_record.strategies_applied = json.dumps(strategies_applied)
            upload_history_record.chunks_count = json.dumps(chunks_count)
            database_session.commit()
    except Exception as exception:
        upload_history_record = database_session.query(UploadHistory).filter(UploadHistory.id == history_id).first()
        if upload_history_record:
            upload_history_record.status = "failed"
            upload_history_record.error_message = str(exception)
            database_session.commit()
    finally:
        database_session.close()


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="RAG 문서 업로드 및 다중 청킹 저장",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    strategies: str = Form(..., description="JSON format chunking strategies list"),
    database_session: Session = Depends(get_database_session),
):
    try:
        content = await file.read()
        filename = file.filename

        try:
            strategy_list = json.loads(strategies)
        except Exception:
            raise HTTPException(
                status_code=400, detail="Invalid JSON format for 'strategies'"
            )

        # 1. Create upload history record in processing state
        upload_history_record = UploadHistory(
            filename=filename,
            status="processing",
            strategies_applied=json.dumps([]),
            chunks_count=json.dumps({}),
        )
        database_session.add(upload_history_record)
        database_session.commit()
        database_session.refresh(upload_history_record)

        # 2. Add chunking & embedding job to background tasks
        background_tasks.add_task(
            process_upload_task,
            upload_history_record.id,
            content,
            filename,
            strategy_list,
        )

        return UploadResponse(
            status="success",
            filename=filename,
            history_id=upload_history_record.id,
            message="File upload accepted. Processing text chunking and embedding in the background.",
        )
    except Exception as exception:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(exception)}")


@router.get("/upload/status/{history_id}", summary="업로드 상태 조회")
async def get_upload_status(history_id: int, database_session: Session = Depends(get_database_session)):
    upload_history_record = database_session.query(UploadHistory).filter(UploadHistory.id == history_id).first()
    if not upload_history_record:
        raise HTTPException(status_code=404, detail="Upload history not found")
    return {
        "id": upload_history_record.id,
        "filename": upload_history_record.filename,
        "status": upload_history_record.status,
        "error_message": upload_history_record.error_message,
        "strategies_applied": json.loads(upload_history_record.strategies_applied) if upload_history_record.strategies_applied else [],
        "chunks_count": json.loads(upload_history_record.chunks_count) if upload_history_record.chunks_count else {},
        "created_at": upload_history_record.created_at.isoformat(),
    }
