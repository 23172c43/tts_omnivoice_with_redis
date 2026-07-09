import logging

from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException, status
from app.models.tts import TTSRequest, TTSResponse
from app.worker.tts_tasks import process_tts_task
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["Text-to-Speech"])


@router.post("/generate", response_model=TTSResponse, status_code=status.HTTP_200_OK)
async def generate_tts(request: TTSRequest):
    """
    Day van ban vao hang doi de chuyen doi giong noi (TTS).
    Task duoc xu ly bat dong bo boi Celery worker.
    """
    try:
        task = process_tts_task.delay(request.text, request.voice_id, request.speed)
        logger.info("Da tao task %s: text=%s...", task.id, request.text[:50])
    except Exception as exc:
        logger.error("Khong the gui task den Celery: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dich vu tam thoi khong kha dung. Vui long thu lai sau.",
        )

    return TTSResponse(
        task_id=task.id,
        status="processing",
        message="Task da duoc dua vao hang doi.",
    )


@router.get("/status/{task_id}", response_model=TTSResponse)
async def get_task_status(task_id: str):
    """
    Kiem tra trang thai va lay ket qua am thanh cua mot task TTS.
    """
    try:
        result = AsyncResult(task_id, app=celery_app)
    except Exception as exc:
        logger.error("Loi khi truy van task %s: %s", task_id, exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} khong ton tai.",
        )

    response_data = {
        "task_id": task_id,
        "status": result.status.lower(),
        "audio_url": None,
        "message": None,
    }

    if result.status == "SUCCESS":
        task_result = result.result or {}
        response_data["status"] = "success"
        response_data["audio_url"] = task_result.get("audio_url")
        response_data["message"] = task_result.get("message")

    elif result.status == "FAILURE":
        response_data["status"] = "error"
        task_result = result.result
        if isinstance(task_result, Exception):
            response_data["message"] = str(task_result)
        elif isinstance(task_result, dict):
            response_data["message"] = task_result.get("error", str(task_result))
        else:
            response_data["message"] = str(task_result) if task_result else "Loi khong xac dinh"

    return TTSResponse(**response_data)