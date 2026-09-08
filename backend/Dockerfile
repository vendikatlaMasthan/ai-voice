# ==============================================================================
# AASIST Anti-Spoofing Backend Container for Hugging Face Spaces / Docker
# ==============================================================================

FROM python:3.10-slim-bookworm

# 1. Install system dependencies for audio decoding (libsndfile, ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Set up a non-root user (required for Hugging Face Spaces, UID 1000)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

# 3. Install Python dependencies
COPY --chown=user requirements.txt requirements.txt
RUN pip install --no-cache-dir --user --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# 4. Copy backend and AASIST codebase
COPY --chown=user backend/ backend/

# 5. Expose Hugging Face Spaces standard port 7860
EXPOSE 7860

# 6. Launch FastAPI server with uvicorn
CMD ["uvicorn", "backend.main_api:app", "--host", "0.0.0.0", "--port", "7860"]
