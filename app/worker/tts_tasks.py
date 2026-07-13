"""
Celery Task cho TTS - Xu ly generate audio bat dong bo.

Chuc nang:
- Non-streaming: Generate full audio, gui 1 lan cho LipSync
- Streaming: Generate tung chunk, gui tung chunk cho LipSync
"""

import logging

import httpx

from app.worker.celery_app import celery_app
from app.services.omnivoice_service import generate_speech, generate_streaming

logger = logging.getLogger(__name__)

# URL cua LipSync service (trong Docker)
LIPSYNC_URL = "http://lipsync:8003"


@celery_app.task(name="process_tts_task", bind=True, max_retries=2)
def process_tts_task(self, text: str, voice_id: str = None, speed: float = None, stream: bool = False):
    """
    Celery task de xu ly yeu cau TTS.

    Quy trinh:
    1. Load model vao GPU (neu chua co)
    2. Neu stream=True: generate tung chunk, gui tung chunk
    3. Neu stream=False: generate full, gui 1 lan
    4. Tra ve ket qua hoac loi

    Args:
        text: Van ban can chuyen thanh giong noi
        voice_id: ID cua voice (default: "001")
        speed: Toc do doc (hien tai chua ho tro)
        stream: Bat streaming mode (True: generate tung chunk)

    Returns:
        dict voi:
            - status: "success" hoac "error"
            - lipsync_response: Phan hoi tu LipSync (neu thanh cong)
            - message: Thong bao loi (neu that bai)

    Note:
        - Neu loi CUDA -> retry sau 60s
        - Chi retry loi CUDA/memory, loi khac tra ve error ngay
    """
    try:
        logger.info("Bat dau task TTS: text=%s, voice_id=%s, stream=%s",
                     text[:50], voice_id, stream)

        if stream:
            # Streaming - generate tung chunk, gui ngay
            return _handle_streaming(text, voice_id)
        else:
            # Non-streaming - generate full, gui 1 lan
            return _handle_non_streaming(text, voice_id, speed)

    except Exception as exc:
        logger.error("Task TTS that bai: %s", exc, exc_info=True)

        # Chi retry loi CUDA/memory (do GPU het bo nho)
        if "CUDA" in str(exc) or "memory" in str(exc).lower():
            raise self.retry(exc=exc, countdown=60)

        return {"status": "error", "message": str(exc)}


def _handle_streaming(text: str, voice_id: str) -> dict:
    """
    Xu ly streaming: generate tung chunk, gui tung chunk cho LipSync.

    Args:
        text: Van ban can generate
        voice_id: ID cua voice

    Returns:
        dict voi status va so chunk da gui
    """
    chunks_sent = 0

    for chunk in generate_streaming(text, voice_id):
        try:
            # Gui chunk den LipSync
            files = {"audio": ("chunk.wav", chunk, "audio/wav")}
            response = httpx.post(
                f"{LIPSYNC_URL}/api/lipsync/chunk",
                files=files,
                timeout=30,
            )
            response.raise_for_status()  # Neu 4xx/5xx -> exception
            chunks_sent += 1
            logger.info("Sent chunk %d thanh cong", chunks_sent)

        except httpx.HTTPError as exc:
            logger.error("Loi gui chunk %d: %s", chunks_sent + 1, exc)
            # Khong tra ve error ngay, van gui chunk khac

    return {
        "status": "success",
        "mode": "streaming",
        "chunks_sent": chunks_sent,
        "message": f"Da gui {chunks_sent} chunks den LipSync",
    }


def _handle_non_streaming(text: str, voice_id: str, speed: float) -> dict:
    """
    Xu ly non-streaming: generate full audio, gui 1 lan.

    Args:
        text: Van ban can generate
        voice_id: ID cua voice
        speed: Toc do doc

    Returns:
        dict voi status va phan hoi tu LipSync
    """
    # Generate full audio
    result = generate_speech(text, voice_id, speed)

    if result["status"] != "success" or not result.get("audio_buffer"):
        return result

    # Gui den LipSync
    try:
        files = {"audio": ("output.wav", result["audio_buffer"], "audio/wav")}
        response = httpx.post(
            f"{LIPSYNC_URL}/api/lipsync",
            files=files,
            timeout=30,
        )
        response.raise_for_status()

        return {
            "status": "success",
            "lipsync_response": response.json(),
            "message": "Gui LipSync thanh cong",
        }
    except httpx.HTTPError as exc:
        logger.error("Loi gui LipSync: %s", exc)
        return {"status": "error", "message": f"Loi gui LipSync: {exc}"}
