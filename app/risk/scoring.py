"""
Risk Scoring & Multi-Signal Fusion Engine for VoiceShield (Phase 3).

Combines acoustic deepfake probabilities, speaker mismatch flags, prosody anomaly scores,
and contextual fraud signals into an explainable, normalized risk score (0–100).
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.risk.context import CallContext, ContextEvaluation, RuleBasedContextAnalyzer


@dataclass
class RiskEngineConfig:
    """
    Configuration parameters and signal weights for risk computation.
    
    NOTE ON WEIGHT SELECTION:
    The weights below (w1=0.5, w2=0.3, w3=0.1, w4=0.1) and scaling constants (100, 100, 50, 50)
    are illustrative baseline defaults specified in the SIH 2026 Problem Statement 26104 roadmap.
    They represent initial prototype values designed for explainable risk aggregation and are fully
    configurable so they can be fine-tuned or calibrated against empirical fraud datasets in future phases.
    """
    # Signal Weights (Illustrative prototype parameters)
    w_fake: float = 0.5          # Weight w1 for Synthetic Voice Probability (P_fake)
    w_mismatch: float = 0.3      # Weight w2 for Speaker Mismatch Flag (M)
    w_acoustic: float = 0.1      # Weight w3 for Acoustic/Prosody Anomaly Score (A)
    w_context: float = 0.1       # Weight w4 for Context/Fraud Flag (C)

    # Scaling Factors
    scale_fake: float = 100.0
    scale_mismatch: float = 100.0
    scale_acoustic: float = 50.0
    scale_context: float = 50.0

    # Risk Level Categorization Thresholds (Illustrative prototype ranges)
    # 0 - 39   -> LOW
    # 40 - 69  -> MEDIUM
    # 70 - 100 -> HIGH
    low_threshold: float = 39.0
    medium_threshold: float = 69.0

    # Diagnostic flag activation thresholds
    fake_prob_flag_threshold: float = 0.60
    acoustic_anomaly_flag_threshold: float = 0.50


@dataclass
class RiskSignals:
    """
    Core input signals for risk calculation.
    
    Attributes:
        fake_probability (P_fake): Synthetic voice probability from deepfake detector [0.0, 1.0].
        speaker_mismatch (M): Speaker mismatch binary flag (0 = match, 1 = mismatch).
                              Supplied as an input in Phase 3 prior to full verification model linking.
        acoustic_anomaly (A): Prosody/acoustic irregularity score [0.0, 1.0].
        context_flag (C): Context/fraud indicator score [0.0, 1.0] from rule-based context analysis.
    """
    fake_probability: float = 0.0
    speaker_mismatch: int = 0
    acoustic_anomaly: float = 0.0
    context_flag: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fake_probability": round(float(self.fake_probability), 4),
            "speaker_mismatch": int(self.speaker_mismatch),
            "acoustic_anomaly": round(float(self.acoustic_anomaly), 4),
            "context_flag": round(float(self.context_flag), 4),
        }


@dataclass
class RiskAssessment:
    """
    Standardized risk evaluation response.
    """
    risk_score: int                     # Normalized integer score clamped between 0 and 100
    risk_level: str                     # "LOW", "MEDIUM", or "HIGH"
    signals: Dict[str, Any]             # Component signals dictionary
    flags: List[str]                    # Human-readable explanation reasons
    recommended_action: str             # Action directive ("ALLOW", "CHALLENGE_CALLER", "SECONDARY_VERIFICATION")
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "signals": self.signals,
            "flags": self.flags,
            "recommended_action": self.recommended_action,
            "metadata": self.metadata,
        }


class VoiceShieldRiskEngine:
    """
    Multi-signal fusion engine that calculates the composite Risk Score and determines
    appropriate operational escalation actions.
    """

    def __init__(
        self,
        config: Optional[RiskEngineConfig] = None,
        context_analyzer: Optional[RuleBasedContextAnalyzer] = None,
    ):
        self.config = config or RiskEngineConfig()
        self.context_analyzer = context_analyzer or RuleBasedContextAnalyzer()

    def calculate_score(self, signals: RiskSignals) -> float:
        """
        Calculates raw composite risk score based on the roadmap formula:
        
        RiskScore = (w1 * 100 * P_fake) + (w2 * 100 * M) + (w3 * 50 * A) + (w4 * 50 * C)
        
        Clamps result strictly to [0.0, 100.0].
        """
        # Ensure values are within normalized bounds
        p_fake = max(0.0, min(1.0, float(signals.fake_probability)))
        m_mismatch = 1.0 if int(signals.speaker_mismatch) >= 1 else 0.0
        a_acoustic = max(0.0, min(1.0, float(signals.acoustic_anomaly)))
        c_context = max(0.0, min(1.0, float(signals.context_flag)))

        raw_score = (
            (self.config.w_fake * self.config.scale_fake * p_fake)
            + (self.config.w_mismatch * self.config.scale_mismatch * m_mismatch)
            + (self.config.w_acoustic * self.config.scale_acoustic * a_acoustic)
            + (self.config.w_context * self.config.scale_context * c_context)
        )

        # Strictly clamp final score to 0 - 100
        clamped_score = max(0.0, min(100.0, raw_score))
        return clamped_score

    def determine_risk_level(self, score: float) -> str:
        """
        Maps numerical score to discrete risk tier:
        - 0 to 39   -> LOW
        - 40 to 69  -> MEDIUM
        - 70 to 100 -> HIGH
        """
        if score <= self.config.low_threshold:
            return "LOW"
        elif score <= self.config.medium_threshold:
            return "MEDIUM"
        else:
            return "HIGH"

    def determine_action(
        self,
        risk_level: str,
        flags: List[str],
        auto_block: bool = False,
        is_auto_hold: bool = False,
        step_up_required: bool = True,
    ) -> str:
        """
        Determines the recommended security workflow action based on risk level and policy.
        """
        if auto_block or risk_level == "CRITICAL":
            return "BLOCK"
        if risk_level == "HIGH":
            return "SECONDARY_VERIFICATION"
        elif risk_level == "MEDIUM":
            return "CHALLENGE_CALLER"
        else:
            return "ALLOW"

    def evaluate_signals(
        self,
        signals: RiskSignals,
        context_reasons: Optional[List[str]] = None,
        prosody_reasons: Optional[List[str]] = None,
        policy_context: Optional[CallContext] = None,
    ) -> RiskAssessment:
        """
        Evaluates pre-assembled risk signals and returns a comprehensive RiskAssessment.
        """
        raw_score = self.calculate_score(signals)
        rounded_score = int(round(raw_score))
        risk_level = self.determine_risk_level(raw_score)

        # Policy thresholds with safe fallbacks
        fake_crit_thresh = policy_context.fake_prob_critical_threshold if policy_context else 0.85
        fake_warn_thresh = policy_context.fake_prob_warn_threshold if policy_context else self.config.fake_prob_flag_threshold
        acoustic_sens_thresh = policy_context.acoustic_anomaly_sensitivity if policy_context else self.config.acoustic_anomaly_flag_threshold
        auto_block_crit = policy_context.auto_block_on_critical_deepfake if policy_context else False
        step_up_required = policy_context.step_up_verification_required if policy_context else True

        # Collect explainable diagnostic flags
        flags: List[str] = []

        if policy_context and signals.fake_probability >= fake_crit_thresh:
            flags.append(f"Critical synthetic voice clone detected ({signals.fake_probability * 100:.1f}%)")
        elif signals.fake_probability >= fake_warn_thresh:
            flags.append(f"High synthetic voice probability ({signals.fake_probability * 100:.1f}%)")
        elif signals.fake_probability >= 0.35:
            flags.append(f"Elevated synthetic voice indicators ({signals.fake_probability * 100:.1f}%)")

        if int(signals.speaker_mismatch) == 1:
            flags.append("Speaker mismatch (voice biometrics do not match claimed profile)")

        if signals.acoustic_anomaly >= acoustic_sens_thresh:
            if prosody_reasons:
                flags.extend(prosody_reasons)
            else:
                flags.append(f"Prosodic/acoustic anomaly detected ({signals.acoustic_anomaly:.2f})")

        if signals.context_flag >= 0.5 or (context_reasons and len(context_reasons) > 0):
            if context_reasons:
                flags.extend(context_reasons)
            else:
                flags.append("Suspicious transaction or authority context")

        # Determine auto-block and auto-hold conditions from policy
        auto_block_trigger = bool(
            policy_context and auto_block_crit and signals.fake_probability >= fake_crit_thresh
        )
        is_auto_hold_trigger = False
        if policy_context and policy_context.requested_transaction_amount and policy_context.transaction_auto_hold_amount:
            if policy_context.requested_transaction_amount >= policy_context.transaction_auto_hold_amount:
                is_auto_hold_trigger = True

        recommended_action = self.determine_action(
            risk_level=risk_level,
            flags=flags,
            auto_block=auto_block_trigger,
            is_auto_hold=is_auto_hold_trigger,
            step_up_required=step_up_required,
        )

        return RiskAssessment(
            risk_score=rounded_score,
            risk_level=risk_level,
            signals=signals.to_dict(),
            flags=flags,
            recommended_action=recommended_action,
            metadata={
                "formula": "w1*100*P_fake + w2*100*M + w3*50*A + w4*50*C",
                "weights": {
                    "w1_fake": self.config.w_fake,
                    "w2_mismatch": self.config.w_mismatch,
                    "w3_acoustic": self.config.w_acoustic,
                    "w4_context": self.config.w_context,
                },
                "thresholds": {
                    "low_max": self.config.low_threshold,
                    "medium_max": self.config.medium_threshold,
                    "high_min": self.config.medium_threshold + 1,
                    "fake_prob_critical": fake_crit_thresh,
                    "fake_prob_warn": fake_warn_thresh,
                    "acoustic_sensitivity": acoustic_sens_thresh,
                },
                "raw_calculated_score": round(raw_score, 2),
                "is_prototype_weights": True,
            },
        )

    def evaluate(
        self,
        fake_probability: float,
        speaker_mismatch: int = 0,
        acoustic_anomaly: float = 0.0,
        context: Optional[CallContext] = None,
        context_flag: Optional[float] = None,
        prosody_reasons: Optional[List[str]] = None,
    ) -> RiskAssessment:
        """
        Convenience endpoint to evaluate call risks directly with optional CallContext.
        """
        context_reasons: List[str] = []

        if context is not None:
            context_eval: ContextEvaluation = self.context_analyzer.analyze(context)
            resolved_context_flag = context_eval.context_flag
            context_reasons = context_eval.flags
        elif context_flag is not None:
            resolved_context_flag = float(context_flag)
        else:
            resolved_context_flag = 0.0

        signals = RiskSignals(
            fake_probability=fake_probability,
            speaker_mismatch=speaker_mismatch,
            acoustic_anomaly=acoustic_anomaly,
            context_flag=resolved_context_flag,
        )

        return self.evaluate_signals(
            signals,
            context_reasons=context_reasons,
            prosody_reasons=prosody_reasons,
            policy_context=context,
        )

