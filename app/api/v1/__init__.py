from fastapi import APIRouter
from app.api.v1.endpoints import tts, health, voices

# Tạo router cho phiên bản v1
router = APIRouter()

# Include các router con
router.include_router(tts.router)
router.include_router(health.router)
router.include_router(voices.router)