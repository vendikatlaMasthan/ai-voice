# ==============================================================================
# VoiceShield AI - Production Backend Container (Docker / Hugging Face / Render)
# ==============================================================================

FROM python:3.10-slim-bookworm

# 1. Install system dependencies for audio & video decoding (libsndfile, ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    libsndfile1-dev \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Set up a non-root user (compatible with Hugging Face Spaces & Render, UID 1000)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

# 3. Install Python dependencies
COPY --chown=user backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir --user --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# 4. Copy backend, core app modules, and AASIST models
COPY --chown=user backend/ backend/
COPY --chown=user app/ app/

# 5. Expose default port (7860 for HF Spaces, Render sets $PORT dynamically)
EXPOSE 7860

# 6. Launch FastAPI server with uvicorn respecting dynamic $PORT
CMD ["sh", "-c", "uvicorn backend.main_api:app --host 0.0.0.0 --port ${PORT:-7860}"]
