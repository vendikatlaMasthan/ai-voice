"""
AASIST Anti-Spoofing FastAPI Backend.
Wraps the pretrained AASIST (Audio Anti-Spoofing using Integrated Spectro-Temporal Graph Attention Networks)
model into a lightweight, production-ready REST API for voice cloning and deepfake detection.

All incoming audio (WebM, Opus, MP3, WAV, M4A, OGG, AAC, FLAC) is routed through a single,
shared FFmpeg conversion pipeline to produce normalized 16kHz mono PCM before downstream inference.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add aasist package to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
AASIST_DIR = CURRENT_DIR / "aasist"
if str(AASIST_DIR) not in sys.path:
    sys.path.insert(0, str(AASIST_DIR))

# Import AASIST model
try:
    from models.AASIST import Model as AASISTModel
except ImportError:
    from backend.aasist.models.AASIST import Model as AASISTModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("AASIST-API")

app = FastAPI(
    title="AASIST Voice Anti-Spoofing API",
    description="Real-time synthetic voice and deepfake detection powered by AASIST (ASVspoof 2019 benchmark).",
    version="1.1.0",
)

# Configure CORS
ALLOWED_ORIGINS = [
    "https://vendikatlamasthan.github.io",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model state
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model: Optional[torch.nn.Module] = None
NB_SAMP = 64600  # Expected sample length (~4.0375s at 16kHz)
TARGET_SR = 16000
MIN_AUDIO_DURATION_SEC = 0.8  # Minimum audio duration for reliable assessment


def decode_audio_to_16k_mono(audio_bytes: bytes, filename: str = "audio") -> np.ndarray:
    """
    Universal Shared Audio Decoding Pipeline.
    Converts any audio format (WebM/Opus, MP3, WAV, M4A, OGG, AAC, FLAC) to a 16kHz mono float32 array in [-1.0, 1.0].
    
    1. Direct in-memory pipe via FFmpeg (fastest, zero disk I/O).
    2. Tempfile fallback for container formats requiring container header seeks.
    """
    if not audio_bytes or len(audio_bytes) < 64:
        raise ValueError("Audio payload is empty or corrupted.")

    # 1. Pipe-based in-memory ffmpeg decoding
    cmd_pipe = [
        "ffmpeg",
        "-nostdin",
        "-v", "error",
        "-i", "pipe:0",
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ar", str(TARGET_SR),
        "-ac", "1",
        "pipe:1"
    ]
    try:
        proc = subprocess.Popen(
            cmd_pipe,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        out_bytes, err_bytes = proc.communicate(input=audio_bytes, timeout=12)
        if proc.returncode == 0 and len(out_bytes) >= 2:
            return np.frombuffer(out_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    except Exception as e:
        logger.debug(f"Direct pipe decode failed for {filename}, falling back to file buffer: {e}")

    # 2. File-based ffmpeg decoding fallback
    ext = Path(filename).suffix or ".tmp"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_in:
        tmp_in_path = tmp_in.name
        tmp_in.write(audio_bytes)
        tmp_in.flush()

    try:
        cmd_file = [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-v", "error",
            "-i", tmp_in_path,
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ar", str(TARGET_SR),
            "-ac", "1",
            "pipe:1"
        ]
        proc = subprocess.Popen(
            cmd_file,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        out_bytes, err_bytes = proc.communicate(timeout=12)
        if proc.returncode == 0 and len(out_bytes) >= 2:
            return np.frombuffer(out_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        err_msg = err_bytes.decode("utf-8", errors="ignore").strip()
        logger.error(f"FFmpeg decoding failure for {filename}: {err_msg}")
        raise ValueError(f"FFmpeg returned non-zero code ({proc.returncode}): {err_msg}")
    finally:
        try:
            if os.path.exists(tmp_in_path):
                os.remove(tmp_in_path)
        except Exception:
            pass


def pad_audio(x: np.ndarray, max_len: int = NB_SAMP) -> np.ndarray:
    """Pad or slice audio to match AASIST input length (64,600 samples)."""
    x_len = len(x)
    if x_len >= max_len:
        return x[:max_len]
    num_repeats = int(max_len / (x_len if x_len > 0 else 1)) + 1
    padded = np.tile(x, num_repeats)[:max_len]
    return padded


def load_aasist_model() -> torch.nn.Module:
    """Instantiate and load pretrained AASIST weights."""
    config_path = AASIST_DIR / "config" / "AASIST.conf"
    weights_path = AASIST_DIR / "models" / "weights" / "AASIST.pth"

    if not config_path.exists():
        raise FileNotFoundError(f"AASIST config not found at: {config_path}")

    with open(config_path, "r") as f:
        config_data = json.load(f)

    model_config = config_data["model_config"]
    net = AASISTModel(model_config).to(device)

    if not weights_path.exists():
        raise FileNotFoundError(
            f"Pretrained weights missing at {weights_path}. "
            f"Please ensure AASIST.pth is located in models/weights/."
        )

    logger.info(f"Loading AASIST weights from {weights_path} onto {device}...")
    checkpoint = torch.load(weights_path, map_location=device)
    net.load_state_dict(checkpoint)
    net.eval()
    logger.info("AASIST model loaded and ready for inference.")
    return net


@app.on_event("startup")
def startup_event():
    global model
    try:
        model = load_aasist_model()
    except Exception as e:
        logger.error(f"Failed to load AASIST model on startup: {e}", exc_info=True)


@app.get("/health")
@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy" if model is not None else "degraded",
        "model": "AASIST",
        "device": str(device),
        "weights_loaded": model is not None,
    }


@app.get("/")
def root():
    return {
        "service": "AASIST Voice Anti-Spoofing API",
        "status": "online",
        "docs_url": "/docs",
    }


class AnalysisResponse(BaseModel):
    spoof_probability: float
    label: str  # "bonafide" | "spoof"
    model: str  # "AASIST"
    bonafide_probability: Optional[float] = None
    inference_device: Optional[str] = None


@app.post("/api/analyze", response_model=AnalysisResponse)
@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_audio(file: UploadFile = File(...)):
    """
    Accepts uploaded audio (WebM, Opus, MP3, WAV, M4A, etc.), converts it via the
    shared 16kHz mono FFmpeg pipeline, pads to 64,600 samples, runs AASIST inference,
    and returns spoof_probability and label.
    """
    global model
    if model is None:
        try:
            model = load_aasist_model()
        except Exception as err:
            logger.error(f"Failed to initialize model: {err}", exc_info=True)
            raise HTTPException(
                status_code=503,
                detail="VoiceShield detection engine is currently initializing. Please try again shortly.",
            )

    if not file.filename:
        raise HTTPException(status_code=400, detail="Please select an audio file to analyze.")

    # 1. Ingest audio payload
    try:
        contents = await file.read()
        if len(contents) < 64:
            raise HTTPException(status_code=400, detail="Audio file is empty. Please provide a valid recording.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading upload stream for '{file.filename}': {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="We couldn't process this audio file. Please try again.")

    # 2. Universal shared FFmpeg conversion to 16kHz mono float32
    try:
        waveform = decode_audio_to_16k_mono(contents, filename=file.filename)
    except Exception as e:
        logger.error(f"Audio decoding failure for file '{file.filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="We couldn't process this audio format. Please check your microphone or try a WAV, MP3, or WebM file.",
        )

    # 3. Duration & quality validation
    duration_sec = len(waveform) / float(TARGET_SR)
    if duration_sec < MIN_AUDIO_DURATION_SEC:
        raise HTTPException(
            status_code=400,
            detail="The voice recording is too short. Please speak for at least 2 to 3 seconds for reliable analysis.",
        )

    # 4. Check for near-silent audio (RMS < 0.001)
    rms = float(np.sqrt(np.mean(waveform ** 2)))
    if rms < 0.001:
        raise HTTPException(
            status_code=400,
            detail="The recording appears silent or inaudible. Please speak closer to your microphone and try again.",
        )

    # 5. Format to AASIST input length (64,600 samples)
    processed_audio = pad_audio(waveform, max_len=NB_SAMP)
    input_tensor = torch.FloatTensor(processed_audio).unsqueeze(0).to(device)

    # 6. AASIST forward inference
    try:
        with torch.no_grad():
            _, output = model(input_tensor)
            probs = F.softmax(output, dim=-1)
            prob_spoof = float(probs[0, 0].item())
            prob_bonafide = float(probs[0, 1].item())
    except Exception as e:
        logger.error(f"AASIST inference failure on '{file.filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="We encountered an issue analyzing this voice sample. Please try again in a few moments.",
        )

    label = "spoof" if prob_spoof >= 0.5 else "bonafide"

    return AnalysisResponse(
        spoof_probability=round(prob_spoof, 4),
        label=label,
        model="AASIST",
        bonafide_probability=round(prob_bonafide, 4),
        inference_device=str(device),
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main_api:app", host="0.0.0.0", port=port, reload=False)
