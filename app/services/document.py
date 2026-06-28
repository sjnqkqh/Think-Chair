import json
import logging
from typing import List
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.services.chunking import ChunkingService
from app.core.vectorstore import VectorStoreManager
from app.models.history import UploadHistory
from app.services.rag import RagService

logger = logging.getLogger(__name__)


class DocumentService:
    @staticmethod
    def create_upload_history(
        database_session: Session, filename: str
    ) -> UploadHistory:
        upload_history_record = UploadHistory(
            filename=filename,
            status="processing",
            strategies_applied=json.dumps([]),
            chunks_count=json.dumps({}),
        )
        database_session.add(upload_history_record)
        database_session.commit()
        database_session.refresh(upload_history_record)
        return upload_history_record

    @staticmethod
    def get_upload_history(
        database_session: Session, history_id: int
    ) -> type[UploadHistory] | None:
        return (
            database_session.query(UploadHistory)
            .filter(UploadHistory.id == history_id)
            .first()
        )

    @staticmethod
    def process_upload_task(
        database_session: Session,
        history_id: int,
        file_bytes: bytes,
        filename: str,
        strategy_list: list,
    ) -> None:
        try:
            text = ChunkingService.extract_text_from_file(file_bytes, filename)
            vector_manager = VectorStoreManager()
            strategies_applied = []
            chunks_count = {}

            for strategy in strategy_list:
                documents = ChunkingService.split_document(text, strategy, filename)
                collection_name = ChunkingService.get_collection_name_for_strategy(
                    strategy
                )

                document_ids = [
                    f"{filename}_{collection_name}_{i}" for i in range(len(documents))
                ]
                vector_manager.delete_existing_documents(
                    document_ids, collection_name=collection_name
                )
                vector_manager.add_documents_batch(
                    documents, document_ids, collection_name=collection_name
                )

                strategies_applied.append(collection_name)
                chunks_count[collection_name] = len(documents)

            upload_history_record = (
                database_session.query(UploadHistory)
                .filter(UploadHistory.id == history_id)
                .first()
            )
            if upload_history_record:
                upload_history_record.status = "completed"
                upload_history_record.strategies_applied = json.dumps(strategies_applied)
                upload_history_record.chunks_count = json.dumps(chunks_count)
                database_session.commit()

                try:
                    RagService().init_bm25_retriever()
                except Exception as e:
                    logger.warning(f"Failed to reload BM25 retriever: {e}")
        except Exception as exception:
            upload_history_record = (
                database_session.query(UploadHistory)
                .filter(UploadHistory.id == history_id)
                .first()
            )
            if upload_history_record:
                upload_history_record.status = "failed"
                upload_history_record.error_message = str(exception)
                database_session.commit()

    @staticmethod
    def get_all_upload_histories(database_session: Session) -> List[UploadHistory]:
        return (
            database_session.query(UploadHistory)
            .order_by(UploadHistory.id.desc())
            .all()
        )

    @staticmethod
    def delete_document_and_embeddings(
        database_session: Session, history_id: int
    ) -> str:
        upload_history_record = (
            database_session.query(UploadHistory)
            .filter(UploadHistory.id == history_id)
            .first()
        )
        if not upload_history_record:
            raise HTTPException(status_code=404, detail="Upload history not found")

        filename = upload_history_record.filename
        try:
            if upload_history_record.chunks_count:
                chunks_count_dict = json.loads(upload_history_record.chunks_count)
                vector_manager = VectorStoreManager()
                for collection_name, count in chunks_count_dict.items():
                    document_ids = [
                        f"{filename}_{collection_name}_{i}" for i in range(count)
                    ]
                    vector_manager.delete_existing_documents(
                        document_ids, collection_name=collection_name
                    )

            database_session.delete(upload_history_record)
            database_session.commit()

            try:
                RagService().init_bm25_retriever()
            except Exception as e:
                logger.warning(f"Failed to reload BM25 retriever: {e}")

            return filename
        except Exception as exception:
            database_session.rollback()
            raise exception
