from celery import Celery
from kombu import Queue

from app.core.config import settings
from app.core.logging_config import configure_logging

configure_logging()

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

# Keep the rotating file/console handlers configured by the application.
celery_app.conf.worker_hijack_root_logger = False
