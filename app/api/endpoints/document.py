import json
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session

from app.schemas.rag import UploadResponse, UploadStatusResponse
from app.services.document import DocumentService
from app.core.database import get_database_session

router = APIRouter()


def execute_background_upload(
    history_id: int, file_bytes: bytes, filename: str, strategy_list: list
) -> None:
    database_session = next(get_database_session())
    try:
        DocumentService.process_upload_task(
            database_session, history_id, file_bytes, filename, strategy_list
        )
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

        upload_history_record = DocumentService.create_upload_history(database_session, filename)

        background_tasks.add_task(
            execute_background_upload,
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


@router.get(
    "/upload/status/{history_id}",
    response_model=UploadStatusResponse,
    summary="업로드 상태 조회"
)
async def get_upload_status(
    history_id: int,
    database_session: Session = Depends(get_database_session)
):
    upload_history_record = DocumentService.get_upload_history(database_session, history_id)
    if not upload_history_record:
        raise HTTPException(status_code=404, detail="Upload history not found")
        
    return UploadStatusResponse(
        id=upload_history_record.id,
        filename=upload_history_record.filename,
        status=upload_history_record.status,
        error_message=upload_history_record.error_message,
        strategies_applied=json.loads(upload_history_record.strategies_applied) if upload_history_record.strategies_applied else [],
        chunks_count=json.loads(upload_history_record.chunks_count) if upload_history_record.chunks_count else {},
        created_at=upload_history_record.created_at,
    )
