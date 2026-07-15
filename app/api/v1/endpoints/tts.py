"""
TTS API Endpoints - API chuyen van ban thanh giong noi.

Endpoints:
- POST /generate: Tao task TTS (bat dong bo)
- GET /status/{task_id}: Kiem tra trang thai task
- POST /test: Test generate audio (khong qua Celery)
"""

import io
import os
import logging
import uuid
from pathlib import Path

import soundfile as sf
from celery.result import AsyncResult
from fastapi import APIRouter, HTTPException, status

from app.schemas.tts import TTSRequest, TTSResponse
from app.worker.tts_tasks import process_tts_task
from app.worker.celery_app import celery_app
from app.services.omnivoice_service import (
    generate_speech,
    generate_streaming,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["Text-to-Speech"])

# Thu muc luu file test
TEST_OUTPUT_DIR = Path("test_output")
TEST_OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================
# MAIN ENDPOINTS
# ============================================================

@router.post("/generate", response_model=TTSResponse, status_code=status.HTTP_200_OK)
async def generate_tts(request: TTSRequest):
    """
    Tao task TTS de generate audio.

    Quy trinh:
    1. Nhan request voi text va voice_id
    2. Tao Celery task (bat dong bo)
    3. Tra ve task_id de kiem tra trang thai
    4. Client polling /status/{task_id} de lay ket qua

    Args:
        request: TTSRequest voi text, voice_id, speed, stream

    Returns:
        TTSResponse voi task_id va status="processing"

    Example:
        >>> POST /api/v1/tts/generate
        >>> {"text": "Xin chao cac ban", "voice_id": "001"}
        >>> Response: {"task_id": "abc123", "status": "processing"}
    """
    try:
        # Tao Celery task voi cac tham so
        task = process_tts_task.delay(
            request.text,
            request.voice_id,
            request.speed,
            request.stream,
        )
        logger.info(
            "Da tao task %s: text=%s, stream=%s",
            task.id,
            request.text[:50],
            request.stream,
        )
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
    Kiem tra trang thai va lay ket qua cua task TTS.

    Args:
        task_id: ID cua task tu /generate

    Returns:
        TTSResponse voi trang thai hien tai va ket qua (neu hoan thanh)

    Status co the la:
        - processing: Task dang duoc xu ly
        - success: Task thanh cong, co lipsync_response
        - error: Task that bai, co message loi
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
        "message": None,
    }

    if result.status == "SUCCESS":
        # Task thanh cong - lay audio_path tu Ket qua Celery
        task_result = result.result or {}
        response_data["status"] = "success"
        response_data["audio_path"] = task_result.get("audio_path")
        response_data["message"] = task_result.get("message")
        response_data["mode"] = task_result.get("mode")
        response_data["duration"] = task_result.get("duration")

    elif result.status == "FAILURE":
        # Task that bai - lay thong tin loi
        response_data["status"] = "error"
        task_result = result.result
        if isinstance(task_result, Exception):
            response_data["message"] = str(task_result)
        elif isinstance(task_result, dict):
            response_data["message"] = task_result.get("error", str(task_result))
        else:
            response_data["message"] = str(task_result) if task_result else "Loi khong xac dinh"

    return TTSResponse(**response_data)


# ============================================================
# TEST ENDPOINT
# ============================================================

@router.post("/test")
async def test_generate(request: TTSRequest):
    """
    Test endpoint: generate audio va luu file.

    Khong qua Celery, khong gui LipSync.
    Dung de test truc tiep tren local.

    Args:
        request: TTSRequest voi text, voice_id, speed, stream

    Returns:
        dict voi:
            - status: "success"
            - mode: "streaming" hoac "non_streaming"
            - file: Duong dan file da luu
            - voice_id: Voice da su dung

    Example:
        >>> POST /api/v1/tts/test
        >>> {"text": "Xin chao", "voice_id": "001", "stream": true}
        >>> Response: {"status": "success", "mode": "streaming", "chunks": 3, ...}
    """
    try:
        task_id = str(uuid.uuid4())[:8]

        if request.stream:
            # === STREAMING MODE ===
            # Generate tung chunk, luu tung chunk, merge thanh file cuoi
            chunks = []
            for i, chunk in enumerate(generate_streaming(
                request.text,
                request.voice_id,
                max_chars=150,  # Nho de test nhieu chunk
            )):

                # Luu tung chunk
                chunk_path = TEST_OUTPUT_DIR / f"{task_id}_chunk_{i}.wav"
                with open(chunk_path, "wb") as f:
                    f.write(chunk)
                chunks.append(chunk)
                logger.info("Saved chunk %d: %s", i, chunk_path)

            # Merge tat ca chunks thanh 1 file
            if chunks:
                all_audio = []
                for chunk in chunks:
                    data, sr = sf.read(io.BytesIO(chunk))
                    all_audio.append(data)

                import numpy as np
                merged = np.concatenate(all_audio)
                merged_path = TEST_OUTPUT_DIR / f"{task_id}_streaming.wav"
                sf.write(str(merged_path), merged, sr)

                return {
                    "status": "success",
                    "mode": "streaming",
                    "chunks": len(chunks),
                    "file": str(merged_path),
                    "voice_id": request.voice_id,
                }

            return {"status": "error", "message": "Khong generate duoc chunk nao"}

        else:
            # === NON-STREAMING MODE ===
            # Generate full audio, luu 1 file
            result = generate_speech(request.text, request.voice_id, request.speed)

            if result["status"] == "success" and result.get("audio_buffer"):
                file_path = TEST_OUTPUT_DIR / f"{task_id}_full.wav"
                with open(file_path, "wb") as f:
                    f.write(result["audio_buffer"])

                return {
                    "status": "success",
                    "mode": "non_streaming",
                    "file": str(file_path),
                    "voice_id": request.voice_id,
                }
            else:
                return result

    except Exception as exc:
        logger.error("Test generate error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
