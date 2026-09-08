"""
AASIST Anti-Spoofing FastAPI Backend.
Wraps the pretrained AASIST (Audio Anti-Spoofing using Integrated Spectro-Temporal Graph Attention Networks)
model into a lightweight, production-ready REST API for voice cloning and deepfake detection.
"""

import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import soundfile as sf
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AASIST-API")

app = FastAPI(
    title="AASIST Voice Anti-Spoofing API",
    description="Real-time synthetic voice and deepfake detection powered by AASIST (ASVspoof 2019 benchmark).",
    version="1.0.0",
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
    allow_origins=["*"],  # Permissive for frontend integration
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model state
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model: Optional[torch.nn.Module] = None
NB_SAMP = 64600  # Expected sample length (~4.0375s at 16kHz)
TARGET_SR = 16000


def pad_audio(x: np.ndarray, max_len: int = NB_SAMP) -> np.ndarray:
    """Pad or slice audio to match AASIST input length (64,600 samples)."""
    x_len = len(x)
    if x_len >= max_len:
        return x[:max_len]
    num_repeats = int(max_len / max_len if x_len == 0 else max_len / x_len) + 1
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
            f"Please download AASIST.pth from the official repository release."
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
        logger.error(f"Failed to load AASIST model on startup: {e}")


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
    Accepts uploaded audio, converts/resamples to 16kHz mono, pads to 64600 samples,
    runs AASIST anti-spoofing inference, and returns spoof probability and label.
    """
    global model
    if model is None:
        model = load_aasist_model()

    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    # Read uploaded bytes
    try:
        contents = await file.read()
        if len(contents) < 100:
            raise HTTPException(status_code=400, detail="Audio file is empty or corrupted.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    # Decode audio using soundfile, fallback to librosa if needed
    waveform: np.ndarray
    sample_rate: int

    try:
        data, sr = sf.read(io.BytesIO(contents))
        waveform = data
        sample_rate = sr
    except Exception:
        # Fallback to librosa if format is mp3 or other
        try:
            import librosa
            data, sr = librosa.load(io.BytesIO(contents), sr=None, mono=True)
            waveform = data
            sample_rate = sr
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Unable to decode audio format. Please provide a WAV, MP3, or FLAC audio file: {e}",
            )

    # Convert to mono if multi-channel
    if waveform.ndim > 1:
        waveform = np.mean(waveform, axis=1)

    # Resample to 16,000 Hz if necessary
    if sample_rate != TARGET_SR:
        try:
            import librosa
            waveform = librosa.resample(waveform, orig_sr=sample_rate, target_sr=TARGET_SR)
        except Exception:
            try:
                import scipy.signal
                num_output_samples = int(len(waveform) * TARGET_SR / sample_rate)
                waveform = scipy.signal.resample(waveform, num_output_samples)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Resampling failed: {e}")

    # Ensure float32 numpy array
    waveform = np.asarray(waveform, dtype=np.float32)

    # Pad or truncate to 64,600 samples
    processed_audio = pad_audio(waveform, max_len=NB_SAMP)

    # Prepare PyTorch tensor [1, 64600]
    input_tensor = torch.FloatTensor(processed_audio).unsqueeze(0).to(device)

    # Run inference
    try:
        with torch.no_grad():
            _, output = model(input_tensor)
            # output shape: [1, 2], class 0 = spoof, class 1 = bonafide
            probs = F.softmax(output, dim=-1)
            prob_spoof = float(probs[0, 0].item())
            prob_bonafide = float(probs[0, 1].item())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {e}")

    # Determine classification
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
