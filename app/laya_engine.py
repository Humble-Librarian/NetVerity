"""Laya typed decision model adapter and lightweight fallback engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .evidence import TruthValue
from .state import DiagnosticState


class DiagnosticCategory(str, Enum):
    """Categorical domain for Laya choice head."""

    WIFI = "wifi"
    DHCP = "dhcp"
    GATEWAY = "gateway"
    DNS = "dns"
    WAN = "wan"
    LOCAL_DEVICE = "local_device"
    FIREWALL = "firewall"
    PROXY = "proxy"
    PHYSICAL_LINK = "physical_link"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LayaDecisionResult:
    """Strongly typed output from Laya decision modeling."""

    recommended_category: DiagnosticCategory
    category_probabilities: Mapping[str, float]
    urgency_score: float  # Scale 1.0 (Low) to 5.0 (Critical)
    hypothesis_confidence: Mapping[str, float]  # Noul proposition probabilities [0.0, 1.0]
    is_mock: bool = False
    model_name: str = "laya-modernbert-decision"
    raw_output: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommended_category": self.recommended_category.value,
            "category_probabilities": dict(self.category_probabilities),
            "urgency_score": round(self.urgency_score, 2),
            "hypothesis_confidence": {
                k: round(v, 4) for k, v in self.hypothesis_confidence.items()
            },
            "is_mock": self.is_mock,
            "model_name": self.model_name,
            "raw_output": dict(self.raw_output),
        }


# Keywords mapped to diagnostic categories for the deterministic fallback
CATEGORY_KEYWORDS: dict[DiagnosticCategory, tuple[str, ...]] = {
    DiagnosticCategory.WIFI: ("wifi", "wlan", "ssid", "wireless", "connect", "signal", "auth"),
    DiagnosticCategory.DHCP: ("dhcp", "ip", "169.254", "apipa", "address", "assigned", "lease"),
    DiagnosticCategory.GATEWAY: ("gateway", "router", "192.168", "default gateway", "local network"),
    DiagnosticCategory.DNS: ("dns", "domain", "name", "resolve", "nslookup", "google.com", "website"),
    DiagnosticCategory.WAN: ("wan", "isp", "internet", "public", "upstream", "broadband", "down"),
    DiagnosticCategory.FIREWALL: ("firewall", "blocked", "port", "security", "filtered"),
    DiagnosticCategory.PROXY: ("proxy", "socks", "http proxy"),
    DiagnosticCategory.PHYSICAL_LINK: ("ethernet", "cable", "unplugged", "link", "nic"),
}


class LayaEngine:
    """Adapter for Laya non-autoregressive decision model with 0MB VRAM CPU fallback."""

    def __init__(self, force_mock: bool = False, model_path: str | None = None) -> None:
        self.force_mock = force_mock
        self.model_path = model_path
        self._real_model: Any = None
        self._init_backend()

    def _init_backend(self) -> None:
        if self.force_mock:
            return
        try:
            import laya  # type: ignore[import-not-found]
            self._real_model = laya
        except ImportError:
            # Graceful fallback when running in lightweight CPU environment
            self._real_model = None

    @property
    def is_real_available(self) -> bool:
        return self._real_model is not None and not self.force_mock

    def predict(
        self,
        state: DiagnosticState,
        user_symptoms: str = "",
        candidate_hypotheses: Sequence[str] = (),
    ) -> LayaDecisionResult:
        """Evaluate state and symptoms through Laya choice, score, and noul heads."""
        if self.is_real_available:
            try:
                return self._predict_real(state, user_symptoms, candidate_hypotheses)
            except Exception:
                # Fall back to deterministic engine if runtime call fails
                pass
        return self._predict_mock(state, user_symptoms, candidate_hypotheses)

    def _predict_real(
        self,
        state: DiagnosticState,
        user_symptoms: str,
        candidate_hypotheses: Sequence[str],
    ) -> LayaDecisionResult:
        """Call real installed Laya router."""
        # Simulated wrapper conforming to real Laya ModernBERT router signature
        router = self._real_model.Router(model=self.model_path or "convaiinnovations/laya")
        context = f"User problem: {user_symptoms}\nKnown facts: {state.canonical_json()}"
        res = router.predict(
            context,
            questions={
                "category": {
                    "type": "choice",
                    "options": [c.value for c in DiagnosticCategory if c != DiagnosticCategory.UNKNOWN],
                },
                "urgency": {"type": "score", "scale": [1, 5]},
                "hypotheses": {
                    "type": "noul",
                    "propositions": [f"Is {h} the root cause?" for h in candidate_hypotheses],
                },
            },
        )
        return LayaDecisionResult(
            recommended_category=DiagnosticCategory(res.get("category", "unknown")),
            category_probabilities=res.get("category_probs", {}),
            urgency_score=float(res.get("urgency", 3.0)),
            hypothesis_confidence=res.get("hypothesis_probs", {}),
            is_mock=False,
            raw_output=res,
        )

    def _predict_mock(
        self,
        state: DiagnosticState,
        user_symptoms: str,
        candidate_hypotheses: Sequence[str],
    ) -> LayaDecisionResult:
        """Deterministic, lightweight scoring model for 0MB VRAM / CPU execution."""
        text_lower = user_symptoms.lower()
        known = state.truths()

        # 1. Compute category probabilities via keyword + observation matching
        category_scores: dict[str, float] = {}
        for cat, keywords in CATEGORY_KEYWORDS.items():
            base_score = 0.05
            # Text matching boost
            for kw in keywords:
                if kw in text_lower:
                    base_score += 0.35

            # Observation-based boosts
            if cat == DiagnosticCategory.WIFI and known.get("wifi_connected") is TruthValue.FALSE:
                base_score += 0.8
            elif cat == DiagnosticCategory.DHCP and known.get("has_valid_ip") is TruthValue.FALSE:
                base_score += 0.8
            elif cat == DiagnosticCategory.GATEWAY and known.get("gateway_reachable") is TruthValue.FALSE:
                base_score += 0.8
            elif cat == DiagnosticCategory.DNS and known.get("dns_resolution_ok") is TruthValue.FALSE:
                base_score += 0.9
            elif cat == DiagnosticCategory.WAN and known.get("internet_ip_reachable") is TruthValue.FALSE:
                base_score += 0.7

            category_scores[cat.value] = base_score

        # Softmax / Normalize
        total = sum(category_scores.values()) or 1.0
        category_probs = {k: v / total for k, v in category_scores.items()}

        # Top category
        best_cat_str = max(category_probs, key=category_probs.get)  # type: ignore[arg-type]
        best_category = DiagnosticCategory(best_cat_str)

        # 2. Urgency scoring (1.0 to 5.0)
        urgency = 2.0
        if known.get("internet_ip_reachable") is TruthValue.FALSE or known.get("gateway_reachable") is TruthValue.FALSE:
            urgency = 4.0
        if "urgent" in text_lower or "outage" in text_lower or "critical" in text_lower:
            urgency = 5.0

        # 3. Noul proposition probabilities for candidate hypotheses
        hyp_probs: dict[str, float] = {}
        for hyp in candidate_hypotheses:
            prob = 0.2
            if "dns" in hyp and category_probs.get("dns", 0) > 0.25:
                prob = 0.85
            elif "dhcp" in hyp and category_probs.get("dhcp", 0) > 0.25:
                prob = 0.85
            elif "gateway" in hyp and category_probs.get("gateway", 0) > 0.25:
                prob = 0.85
            elif "wifi" in hyp and category_probs.get("wifi", 0) > 0.25:
                prob = 0.85
            elif "wan" in hyp and category_probs.get("wan", 0) > 0.25:
                prob = 0.80
            hyp_probs[hyp] = prob

        return LayaDecisionResult(
            recommended_category=best_category,
            category_probabilities=category_probs,
            urgency_score=urgency,
            hypothesis_confidence=hyp_probs,
            is_mock=True,
            raw_output={"heuristic": "deterministic_keyword_state_matcher"},
        )
