"""
Rule-based Context & Fraud Analysis Module for VoiceShield (Phase 3).
Provides deterministic, explainable evaluation of caller metadata, transaction amounts,
urgency indicators, authority claims, and suspicious keywords without requiring external LLM dependencies.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set


# Default suspicious keywords indicative of social engineering and financial wire fraud (English & Indian Multilingual)
DEFAULT_SUSPICIOUS_KEYWORDS: Set[str] = {
    # English keywords
    "wire immediately",
    "wire transfer",
    "send funds",
    "urgent payment",
    "bypass protocol",
    "bypass procedure",
    "do not tell anyone",
    "keep this confidential",
    "keep this secret",
    "gift card",
    "crypto transfer",
    "otp",
    "one time password",
    "security code",
    "emergency transfer",
    "authorize now",
    "account details",
    "bank transfer",
    "unauthorized transaction",
    # Hindi keywords
    "turant bhejo",
    "paise transfer",
    "otp batao",
    "kisi ko mat batana",
    "gupt rakho",
    "khata sankhya",
    "emergency payment",
    # Telugu keywords
    "ventane pampandi",
    "dabbu pampandi",
    "evariki cheppavaddu",
    "rahasyam",
    "otp cheppandi",
    "khata vivaralu",
    # Tamil keywords
    "udane anuppavum",
    "panam anuppavum",
    "yarukkum sollathe",
    "ragasiyam",
    "otp sollunga",
    # Kannada keywords
    "tara bandisi",
    "hana kalisi",
    "yarigu helabedi",
    "khatheya vivara",
    # Malayalam keywords
    "udane ayakkuka",
    "paisa ayakkuka",
    "aarkkum parayenda",
    # Bengali keywords
    "tahobil pathan",
    "taka pathan",
    "kakeo bolben na",
    "gopon rakhoon",
    # Marathi keywords
    "tatkal pathva",
    "paise pathva",
    "koni sangu naka",
    "gupt theva",
}

# Supported Indian & English Language Registry (Feature 4 Multilingual Readiness)
SUPPORTED_LANGUAGE_OPTIONS = [
    "Auto Detect",
    "English",
    "Hindi",
    "Telugu",
    "Tamil",
    "Kannada",
    "Malayalam",
    "Bengali",
    "Marathi",
]

LANGUAGE_METADATA_REGISTRY = {
    "auto": {
        "canonical_name": "Auto Detect",
        "code": "auto",
        "accent_region": "Adaptive Subcontinental Multi-Dialect Profile",
        "default_detected": "English",
        "confidence": 0.94,
    },
    "english": {
        "canonical_name": "English",
        "code": "en",
        "accent_region": "Indian English (Standard / Subcontinental)",
        "default_detected": "English",
        "confidence": 0.98,
    },
    "hindi": {
        "canonical_name": "Hindi",
        "code": "hi",
        "accent_region": "Indo-Aryan (Northern & Central Region)",
        "default_detected": "Hindi",
        "confidence": 0.96,
    },
    "telugu": {
        "canonical_name": "Telugu",
        "code": "te",
        "accent_region": "Dravidian (Andhra Pradesh & Telangana)",
        "default_detected": "Telugu",
        "confidence": 0.97,
    },
    "tamil": {
        "canonical_name": "Tamil",
        "code": "ta",
        "accent_region": "Dravidian (Tamil Nadu & Southern Region)",
        "default_detected": "Tamil",
        "confidence": 0.97,
    },
    "kannada": {
        "canonical_name": "Kannada",
        "code": "kn",
        "accent_region": "Dravidian (Karnataka Region)",
        "default_detected": "Kannada",
        "confidence": 0.95,
    },
    "malayalam": {
        "canonical_name": "Malayalam",
        "code": "ml",
        "accent_region": "Dravidian (Kerala Region)",
        "default_detected": "Malayalam",
        "confidence": 0.95,
    },
    "bengali": {
        "canonical_name": "Bengali",
        "code": "bn",
        "accent_region": "Indo-Aryan (Eastern Region & West Bengal)",
        "default_detected": "Bengali",
        "confidence": 0.96,
    },
    "marathi": {
        "canonical_name": "Marathi",
        "code": "mr",
        "accent_region": "Indo-Aryan (Western Region & Maharashtra)",
        "default_detected": "Marathi",
        "confidence": 0.96,
    },
}

def resolve_speech_profile(
    selected_language: Optional[str] = None,
    detected_language: Optional[str] = None,
    accent_region_override: Optional[str] = None,
    transcript_text: Optional[str] = None,
    language_confidence: Optional[float] = None,
    transcript_language: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    Deterministically builds non-authoritative multilingual speech profile metadata.
    Does NOT modify or override cryptographic risk scoring, caller recognition,
    verification, fraud history, organization, or policy enforcement.
    """
    raw_sel = str(selected_language or "").strip().lower()
    
    # Map common aliases and ISO codes
    alias_map = {
        "": "auto",
        "auto": "auto",
        "auto detect": "auto",
        "auto_detect": "auto",
        "autodetect": "auto",
        "en": "english",
        "eng": "english",
        "english": "english",
        "hi": "hindi",
        "hin": "hindi",
        "hindi": "hindi",
        "te": "telugu",
        "tel": "telugu",
        "telugu": "telugu",
        "ta": "tamil",
        "tam": "tamil",
        "tamil": "tamil",
        "kn": "kannada",
        "kan": "kannada",
        "kannada": "kannada",
        "ml": "malayalam",
        "mal": "malayalam",
        "malayalam": "malayalam",
        "bn": "bengali",
        "ben": "bengali",
        "bangla": "bengali",
        "bengali": "bengali",
        "mr": "marathi",
        "mar": "marathi",
        "marathi": "marathi",
    }
    
    resolved_key = alias_map.get(raw_sel, "auto")
    meta = LANGUAGE_METADATA_REGISTRY.get(resolved_key, LANGUAGE_METADATA_REGISTRY["auto"])
    
    is_auto = resolved_key == "auto"
    selected_name = meta["canonical_name"]
    
    if is_auto:
        # For auto-detection, determine plausible regional dialect without false claims
        det_name = detected_language or meta["default_detected"]
        active_lang = det_name
        # Match detected language to metadata registry for accent profiling
        det_key = alias_map.get(str(det_name).strip().lower(), "english")
        det_meta = LANGUAGE_METADATA_REGISTRY.get(det_key, LANGUAGE_METADATA_REGISTRY["english"])
        accent_profile = accent_region_override or det_meta["accent_region"]
        confidence = round(float(language_confidence), 2) if language_confidence is not None else round(float(meta["confidence"]), 2)
        code = det_meta["code"]
    else:
        active_lang = selected_name
        det_name = selected_name
        accent_profile = accent_region_override or meta["accent_region"]
        confidence = round(float(language_confidence), 2) if language_confidence is not None else round(float(meta["confidence"]), 2)
        code = meta["code"]

    transcript_lang = transcript_language or (f"{active_lang} (Subcontinental Romanized / Vernacular)" if transcript_text else active_lang)

    return {
        "language": active_lang,
        "language_code": code,
        "selected_language": selected_name,
        "detected_language": det_name,
        "is_auto_detected": is_auto,
        "language_confidence": confidence,
        "accent_region": accent_profile,
        "accent_profile": accent_profile,
        "transcript_language": transcript_lang,
        "is_authoritative": False,
        "disclaimer": "Non-authoritative speech profile metadata for multilingual readiness. Does not alter cryptographic risk evaluation.",
    }

# High-authority roles frequently targeted in executive impersonation (CEO fraud / BEC)
HIGH_AUTHORITY_ROLES: Set[str] = {
    "ceo",
    "chief executive officer",
    "cfo",
    "chief financial officer",
    "director",
    "managing director",
    "vp",
    "vice president",
    "executive",
    "bank manager",
    "compliance officer",
    "it administrator",
    "legal counsel",
}


@dataclass
class CallContext:
    """
    Contextual information regarding the call, caller identity, transaction, and transcript.
    Supports enriched multi-tenant database context and enterprise fraud intelligence.
    """
    caller_id: Optional[str] = None
    is_caller_recognized: bool = True
    is_previously_flagged: bool = False
    claimed_role: Optional[str] = None
    requested_transaction_amount: Optional[float] = None
    normal_transaction_amount: Optional[float] = None
    is_urgent: bool = False
    urgency_reason: Optional[str] = None
    transcript_text: Optional[str] = None
    suspicious_keywords_found: List[str] = field(default_factory=list)
    
    # Enriched Multi-Tenant Database Context & Authoritative Policy (Feature 3)
    organization_id: Optional[str] = None
    contact_id: Optional[str] = None
    contact_name: Optional[str] = None
    contact_role: Optional[str] = None
    is_verified: Optional[bool] = None
    role_mismatch: bool = False
    flag_reason: Optional[str] = None
    transaction_reference: Optional[str] = None
    transaction_auto_hold_amount: Optional[float] = None
    has_prior_fraud_history: bool = False
    fraud_history_count: int = 0
    recent_fraud_types: List[str] = field(default_factory=list)
    context_source: str = "DEFAULT"
    context_available: bool = True

    # Multilingual & Speech Profile Metadata (Feature 4 - Non-Authoritative)
    selected_language: Optional[str] = "Auto Detect"
    language: Optional[str] = None
    detected_language: Optional[str] = None
    language_confidence: Optional[float] = None
    accent_region: Optional[str] = None
    accent_profile: Optional[str] = None
    transcript_language: Optional[str] = None

    # Authoritative Organization Policy Fields
    fake_prob_critical_threshold: float = 0.85
    fake_prob_warn_threshold: float = 0.50
    speaker_verification_strictness: float = 0.65
    acoustic_anomaly_sensitivity: float = 0.70
    step_up_verification_required: bool = True
    auto_block_on_critical_deepfake: bool = False


@dataclass
class ContextEvaluation:
    """
    Result of rule-based context analysis.
    """
    context_flag: float                 # Continuous or discrete flag score in [0.0, 1.0] (0 = benign, 1 = suspicious)
    is_suspicious: bool                 # Boolean decision threshold (context_flag > 0)
    flags: List[str]                    # Human-readable explanation reasons
    severity_score: float               # Raw unweighted context risk penalty
    context_metadata: dict = field(default_factory=dict)


class RuleBasedContextAnalyzer:
    """
    Deterministic context analyzer enforcing explainable anti-fraud rules.
    """

    def __init__(
        self,
        suspicious_keywords: Optional[Set[str]] = None,
        transaction_deviation_multiplier: float = 2.0,
        large_unverified_amount_threshold: float = 10000.0,
    ):
        """
        Args:
            suspicious_keywords: Custom set of lowercase suspicious phrases.
            transaction_deviation_multiplier: Ratio above normal transaction volume that triggers a flag.
            large_unverified_amount_threshold: Flat transaction amount considered high-risk when no historical baseline exists.
        """
        self.suspicious_keywords = suspicious_keywords or DEFAULT_SUSPICIOUS_KEYWORDS
        self.transaction_deviation_multiplier = transaction_deviation_multiplier
        self.large_unverified_amount_threshold = large_unverified_amount_threshold

    def analyze(self, context: CallContext) -> ContextEvaluation:
        """
        Evaluates the call context against deterministic fraud rules.
        """
        flags: List[str] = []
        severity_points: float = 0.0

        # Rule 1: History of prior fraudulent activity or threat intelligence records
        if context.is_previously_flagged or context.has_prior_fraud_history or context.fraud_history_count > 0:
            if context.flag_reason:
                flags.append(f"Caller previously flagged for suspicious activity ({context.flag_reason})")
            elif context.recent_fraud_types:
                types_str = ", ".join(context.recent_fraud_types[:3])
                flags.append(f"Caller ID or identity linked to prior fraud incident records: {types_str}")
            else:
                flags.append("Caller ID or voice history previously flagged for suspicious activity")
            severity_points += 0.8

        # Rule 2: Role verification & executive impersonation
        if context.role_mismatch and context.claimed_role and context.contact_role:
            flags.append(
                f"Role Mismatch: Claimed role '{context.claimed_role}' does not match registered contact role '{context.contact_role}'"
            )
            severity_points += 0.7
        elif not context.is_caller_recognized and context.claimed_role:
            role_lower = context.claimed_role.strip().lower()
            if any(auth_role in role_lower for auth_role in HIGH_AUTHORITY_ROLES):
                flags.append(
                    f"Unrecognized caller asserting high-authority executive role: '{context.claimed_role}'"
                )
                severity_points += 0.7
            else:
                flags.append(f"Unrecognized caller claiming role: '{context.claimed_role}'")
                severity_points += 0.3
        elif not context.is_caller_recognized:
            flags.append("Incoming call from unrecognized/unknown contact")
            severity_points += 0.2

        # Rule 3: Transaction amount anomalies & policy auto-hold limits
        if context.requested_transaction_amount is not None and context.requested_transaction_amount > 0:
            req_amt = context.requested_transaction_amount
            norm_amt = context.normal_transaction_amount
            hold_amt = context.transaction_auto_hold_amount

            # 3a. Organization policy auto-hold check
            if hold_amt is not None and hold_amt > 0 and req_amt >= hold_amt:
                flags.append(
                    f"Requested transaction (${req_amt:,.2f}) exceeds organization auto-hold policy (${hold_amt:,.2f})"
                )
                severity_points += 0.6

            # 3b. Normal historical baseline ratio check
            if norm_amt is not None and norm_amt > 0:
                ratio = req_amt / norm_amt
                if ratio >= self.transaction_deviation_multiplier:
                    flags.append(
                        f"Requested transaction amount (${req_amt:,.2f}) is {ratio:.1f}x higher than normal baseline (${norm_amt:,.2f})"
                    )
                    severity_points += min(0.8, 0.4 * (ratio / self.transaction_deviation_multiplier))
            elif req_amt >= self.large_unverified_amount_threshold:
                flags.append(
                    f"Substantial transaction requested (${req_amt:,.2f}) without established historical baseline"
                )
                severity_points += 0.5

        # Rule 4: High urgency pressure combined with financial or access claims
        if context.is_urgent:
            reason = f" ({context.urgency_reason})" if context.urgency_reason else ""
            flags.append(f"High urgency and immediate execution pressure detected{reason}")
            severity_points += 0.4

        # Rule 5: Keyword & transcript phrase extraction
        detected_keywords: List[str] = []
        if context.suspicious_keywords_found:
            detected_keywords.extend(context.suspicious_keywords_found)

        if context.transcript_text:
            transcript_lower = context.transcript_text.lower()
            for kw in self.suspicious_keywords:
                if kw in transcript_lower and kw not in detected_keywords:
                    detected_keywords.append(kw)

        if detected_keywords:
            flags.append(
                f"Suspicious social engineering keywords detected: {', '.join([repr(k) for k in detected_keywords[:4]])}"
            )
            severity_points += min(0.7, 0.3 * len(detected_keywords))

        # Calculate final normalized context flag C in [0.0, 1.0]
        if not flags:
            context_flag = 0.0
            is_suspicious = False
        else:
            # Map severity score into [0.0, 1.0], clamping discrete activation
            context_flag = round(min(1.0, max(0.0, severity_points)), 2)
            # Binary flag representation (1 if any high-confidence fraud indicator exists, or proportional)
            if context_flag >= 0.5:
                context_flag = 1.0
            is_suspicious = context_flag > 0.0

        speech_prof = resolve_speech_profile(
            selected_language=context.selected_language or context.language,
            detected_language=context.detected_language,
            accent_region_override=context.accent_region or context.accent_profile,
            transcript_text=context.transcript_text,
        )

        metadata = {
            "context_source": context.context_source,
            "context_available": context.context_available,
            "organization_id": context.organization_id,
            "contact_id": context.contact_id,
            "is_verified": context.is_verified,
            "detected_keywords": detected_keywords,
            "speech_profile": speech_prof,
            "language": speech_prof["language"],
            "selected_language": speech_prof["selected_language"],
            "detected_language": speech_prof["detected_language"],
            "language_confidence": speech_prof["language_confidence"],
            "accent_region": speech_prof["accent_region"],
            "accent_profile": speech_prof["accent_profile"],
        }

        return ContextEvaluation(
            context_flag=context_flag,
            is_suspicious=is_suspicious,
            flags=flags,
            severity_score=round(severity_points, 2),
            context_metadata=metadata,
        )
