"""
VoiceShield FastAPI Backend Application Entry Point (Phase 4).

Smart India Hackathon (SIH 2026) — Problem Statement 26104
Real-Time AI Voice Cloning Detection & Multi-Signal Fraud Defense.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.utils.audio_utils import AudioError

app = FastAPI(
    title="VoiceShield API",
    description=(
        "Production AI Voice-Cloning Detection & Anti-Fraud Security Engine. "
        "Integrates 16kHz audio preprocessing, fine-tuned transformer deepfake detection, "
        "deterministic context fraud analysis, and multi-signal risk fusion scoring."
    ),
    version="1.0.0 (Phase 4)",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Cross-Origin Resource Sharing (CORS) setup for local testing and future dashboard integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Centralized Audio Domain Exception Handler
@app.exception_handler(AudioError)
async def audio_error_handler(request: Request, exc: AudioError):
    return JSONResponse(
        status_code=400,
        content={
            "error_type": type(exc).__name__,
            "message": str(exc),
            "detail": "Audio validation failed during processing.",
        },
    )

# Include Phase 4 API Router
app.include_router(api_router, prefix="")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
