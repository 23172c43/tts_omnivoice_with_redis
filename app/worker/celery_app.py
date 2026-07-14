from celery import Celery
from kombu import Queue

from app.core.config import settings

celery_app = Celery(
    "tts_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tts_tasks"],
)

# Dinh nghia queues cho TTS
celery_app.conf.task_queues = [
    Queue("tts_queue"),
]

# Default queue khi gui task khong chi dinh
celery_app.conf.task_default_queue = "tts_queue"
