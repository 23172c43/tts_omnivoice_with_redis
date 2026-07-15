# ============================================================
# OmniVoice TTS — Docker Image
# ============================================================
# Base: PyTorch 2.4 + CUDA 12.1 + cuDNN 9
# Chua ca FastAPI server va Celery worker (khac command)
# ============================================================

FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

# === System deps ===
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# === Working directory ===
WORKDIR /app

# === Python deps ===
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# === App code ===
COPY app/ app/

# === Default: FastAPI server ===
EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
