"""
VoiceShield Multilingual and Indian Speech Profile Management.

Provides explicit support for 8 major Indian language profiles and regional accents:
1. English (Indian Standard / Global)
2. Hindi (हिन्दी)
3. Telugu (తెలుగు)
4. Tamil (தமிழ்)
5. Kannada (ಕನ್ನಡ)
6. Malayalam (മലയാളം)
7. Bengali (বাংলা)
8. Marathi (मराठी)

IMPORTANT SECURITY ARCHITECTURAL INVARIANTS:
- Language/accent metadata is strictly treated as non-authoritative contextual telemetry.
- It MUST NEVER alter authoritative security fields (organization_id, is_verified,
  is_caller_recognized, is_previously_flagged, contact_role, fraud_history_count,
  policy, risk score formula, risk level, or role mismatch flags).
- Acoustic deepfake detection (Wav2Vec2), prosody anomaly analysis, and speaker verification
  (ECAPA-TDNN) operate on acoustic frequency distributions invariant to speech language.
"""

from typing import Dict, Any, Optional

SUPPORTED_LANGUAGES: Dict[str, Dict[str, Any]] = {
    "english": {
        "display_name": "English",
        "native_name": "English (Indian / Global)",
        "code": "en-IN",
        "family": "Indo-European",
    },
    "hindi": {
        "display_name": "Hindi",
        "native_name": "हिन्दी",
        "code": "hi-IN",
        "family": "Indo-Aryan",
    },
    "telugu": {
        "display_name": "Telugu",
        "native_name": "తెలుగు",
        "code": "te-IN",
        "family": "Dravidian",
    },
    "tamil": {
        "display_name": "Tamil",
        "native_name": "தமிழ்",
        "code": "ta-IN",
        "family": "Dravidian",
    },
    "kannada": {
        "display_name": "Kannada",
        "native_name": "ಕನ್ನಡ",
        "code": "kn-IN",
        "family": "Dravidian",
    },
    "malayalam": {
        "display_name": "Malayalam",
        "native_name": "മലയാളം",
        "code": "ml-IN",
        "family": "Dravidian",
    },
    "bengali": {
        "display_name": "Bengali",
        "native_name": "বাংলা",
        "code": "bn-IN",
        "family": "Indo-Aryan",
    },
    "marathi": {
        "display_name": "Marathi",
        "native_name": "मराठी",
        "code": "mr-IN",
        "family": "Indo-Aryan",
    },
}

INDIAN_ACCENT_REGIONS = [
    "Pan-Indian / General",
    "North India (Hindi / Delhi-NCR / UP)",
    "South India (Karnataka / Bangalore)",
    "South India (Telangana / Andhra Pradesh)",
    "South India (Tamil Nadu / Chennai)",
    "South India (Kerala / Malayalam)",
    "East India (West Bengal / Kolkata)",
    "West India (Maharashtra / Mumbai)",
]


def resolve_speech_profile(
    selected_language: Optional[str] = None,
    language: Optional[str] = None,
    detected_language: Optional[str] = None,
    language_confidence: Optional[float] = None,
    accent_region: Optional[str] = None,
    accent_profile: Optional[str] = None,
    transcript_language: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolves the active multilingual speech profile and regional metadata.

    Args:
        selected_language: User or client selected language.
        language: Alias for selected_language.
        detected_language: Automated upstream detector result if available.
        language_confidence: Confidence score of detection (0.0 - 1.0).
        accent_region: Regional accent classification.
        accent_profile: Alias for accent_region.
        transcript_language: Language code from ASR transcript.

    Returns:
        Dict with resolved speech metadata and acoustic invariance flags.
    """
    raw_lang = (selected_language or language or "Auto Detect").strip()
    norm_key = raw_lang.lower().replace(" ", "").replace("-", "")

    matched_key = None
    for key, spec in SUPPORTED_LANGUAGES.items():
        if key in norm_key or spec["display_name"].lower() in norm_key:
            matched_key = key
            break

    if matched_key and matched_key in SUPPORTED_LANGUAGES:
        spec = SUPPORTED_LANGUAGES[matched_key]
        resolved_display = spec["display_name"]
        lang_code = spec["code"]
        family = spec["family"]
    elif "auto" in norm_key or not raw_lang:
        resolved_display = "Auto Detect"
        lang_code = "auto"
        family = "Multilingual (Indian)"
    else:
        resolved_display = "Auto Detect"
        lang_code = "auto"
        family = "Multilingual (Indian)"

    resolved_accent = (accent_region or accent_profile or "Pan-Indian / General").strip()

    return {
        "selected_language": resolved_display,
        "language": resolved_display,
        "language_code": lang_code,
        "family": family,
        "accent_region": resolved_accent,
        "detected_language": detected_language or (resolved_display if resolved_display != "Auto Detect" else None),
        "language_confidence": language_confidence,
        "transcript_language": transcript_language,
        "acoustic_invariance": True,
        "note": "Acoustic deepfake features, prosody anomalies, and ECAPA-TDNN biometric verification operate invariants across Indian multilingual speech.",
    }
