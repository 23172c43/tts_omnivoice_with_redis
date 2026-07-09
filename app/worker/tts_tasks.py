from app.worker.celery_app import celery_app
from app.services.omnivoice_service import generate_speech
import logging

logger = logging.getLogger(__name__)

@celery_app.task(name="process_tts_task", bind=True, max_retries=2)
def process_tts_task(self, text: str, voice_id: str = None, speed: float = None):
    """
    Celery task để xử lý yêu cầu TTS.
    """
    try:
        logger.info("Bat dau task TTS: text=%s, voice_id=%s, speed=%s",
                     text[:50], voice_id, speed)
        result = generate_speech(text, voice_id, speed)
        logger.info("Task TTS hoan thanh: %s", result.get("status"))
        return result
    except Exception as exc:
        logger.error("Task TTS that bai: %s", exc, exc_info=True)
        # Retry nếu là lỗi transient
        if "CUDA" in str(exc) or "memory" in str(exc).lower():
            raise self.retry(exc=exc, countdown=60)
        return {"error": str(exc)}