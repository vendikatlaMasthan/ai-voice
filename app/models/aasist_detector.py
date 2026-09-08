"""
AASIST Anti-Spoofing Detector Integration (Tier 2 in VoiceShield Detection Hierarchy).

Implements forward inference for the AASIST model trained on ASVspoof2019.
Always receives 16kHz mono float32 audio produced by the universal ingestion pipeline.
Contributes to synthetic_voice_score as one input; never produces a standalone verdict.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import torch

from app.audio.preprocessing import PreprocessedAudio

logger = logging.getLogger("VoiceShield.AASIST")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AASIST_DIR = REPO_ROOT / "backend" / "aasist"
CONFIG_PATH = AASIST_DIR / "config" / "AASIST.conf"
WEIGHTS_PATH = AASIST_DIR / "models" / "weights" / "AASIST.pth"

NB_SAMP = 64600  # AASIST input window (~4.0375s at 16kHz)


def pad_waveform(x: np.ndarray, max_len: int = NB_SAMP) -> np.ndarray:
    """Pad or repeat audio to match AASIST input length (64,600 samples)."""
    x_len = len(x)
    if x_len >= max_len:
        return x[:max_len]
    num_repeats = int(max_len / (x_len if x_len > 0 else 1)) + 1
    return np.tile(x, num_repeats)[:max_len]


class AASISTDetector:
    """
    Tier 2 Voice Clone & Anti-Spoofing Detector.
    Wraps the pretrained AASIST model.
    """

    def __init__(self, device: Optional[str] = None):
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model: Optional[torch.nn.Module] = None
        self.is_loaded = False

    def load_model(self) -> bool:
        """Loads AASIST model config and weights."""
        if self.is_loaded and self.model is not None:
            return True

        if not CONFIG_PATH.exists():
            logger.warning(f"AASIST config not found at: {CONFIG_PATH}")
            return False

        if not WEIGHTS_PATH.exists():
            logger.warning(f"AASIST pretrained weights not found at: {WEIGHTS_PATH}")
            return False

        try:
            # Dynamically import AASISTModel from backend.aasist.models.AASIST
            import sys
            if str(REPO_ROOT) not in sys.path:
                sys.path.insert(0, str(REPO_ROOT))
            if str(AASIST_DIR) not in sys.path:
                sys.path.insert(0, str(AASIST_DIR))

            from backend.aasist.models.AASIST import Model as AASISTModel

            with open(CONFIG_PATH, "r") as f:
                config_data = json.load(f)

            model_config = config_data["model_config"]
            net = AASISTModel(model_config).to(self.device)

            logger.info(f"Loading AASIST weights from {WEIGHTS_PATH} onto {self.device}...")
            checkpoint = torch.load(WEIGHTS_PATH, map_location=self.device)
            net.load_state_dict(checkpoint)
            net.eval()
            self.model = net
            self.is_loaded = True
            logger.info("AASIST model successfully initialized.")
            return True
        except Exception as err:
            logger.error(f"Failed to load AASIST model: {err}", exc_info=True)
            self.model = None
            self.is_loaded = False
            return False

    def predict(self, audio: PreprocessedAudio) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Runs inference on 16kHz mono audio.
        
        Returns:
            Tuple of:
                - success: bool
                - result: dict containing:
                    - fake_probability: float [0.0 - 1.0]
                    - real_probability: float [0.0 - 1.0]
                    - model_type: "AASIST"
                    - model_id: "AASIST-ASVspoof2019"
        """
        if not self.is_loaded:
            if not self.load_model():
                return False, None

        try:
            # Ensure 1D numpy float32 array
            arr = np.asarray(audio.waveform, dtype=np.float32)
            if len(arr) < 1600:  # < 0.1s is unworkable
                return False, None

            padded = pad_waveform(arr, NB_SAMP)
            tensor_x = torch.from_numpy(padded).unsqueeze(0).to(self.device)

            with torch.no_grad():
                out_feat, out_logits = self.model(tensor_x)
                probs = torch.softmax(out_logits, dim=1).squeeze(0).cpu().numpy()

            bonafide_prob = float(probs[0])
            spoof_prob = float(probs[1])

            return True, {
                "fake_probability": round(spoof_prob, 4),
                "real_probability": round(bonafide_prob, 4),
                "model_type": "AASIST",
                "model_id": "AASIST-ASVspoof2019",
                "device": str(self.device),
            }
        except Exception as err:
            logger.error(f"AASIST inference execution failed: {err}", exc_info=True)
            return False, None
