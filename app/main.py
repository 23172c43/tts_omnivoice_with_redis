import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import router as v1_router

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# Khong load model o day — service dung lazy-loading roi
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting OmniVoice API...")
    yield
    logger.info("Shutting down OmniVoice API...")


app = FastAPI(
    title="OmniVoice API",
    description="API cho dich vu Text-to-Speech OmniVoice",
    version="1.0.0",
    lifespan=lifespan,
)

# --- CORS (cho phep frontend goi) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "message": "Welcome to the OmniVoice API. Visit /docs for API documentation.",
        "version": "1.0.0",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Vui long thu lai sau."},
    )