import logging
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/")
async def health_check():
    """
    Kiem tra trang thai co ban cua service.
    """
    return {"status": "ok", "message": "Service is running"}


@router.get("/ready")
async def readiness_check():
    """
    Kiem tra service da san sang nhan request chua (model + Redis).
    """
    checks = {"redis": False, "model": False}

    # Check Redis connectivity
    try:
        from app.worker.celery_app import celery_app
        conn = celery_app.connection()
        conn.ensure_connection(timeout=2)
        checks["redis"] = True
        conn.close()
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)

    # Check model files exist
    model_config = (
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "local_models" / "k2-fsa" / "OmniVoice" / "config.json"
    )
    checks["model"] = model_config.exists()

    all_ok = all(checks.values())
    status_code = 200 if all_ok else 503

    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
    }