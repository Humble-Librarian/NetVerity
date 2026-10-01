"""Decision policy engine combining Prolog inference, Laya signals, and BFS planning."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .evidence import TruthValue
from .laya_engine import DiagnosticCategory, LayaDecisionResult, LayaEngine
from .prolog_engine import PrologEngine, PrologResult
from .search_engine import DiagnosticSearchEngine, SearchTrace
from .state import DiagnosticState


class PolicyAction(str, Enum):
    """The concrete action commanded by the policy engine."""

    DIAGNOSE = "diagnose"
    RUN_TEST = "run_test"
    ASK_USER = "ask_user"
    ABSTAIN = "abstain"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Strongly typed output from the hybrid policy engine."""

    action: PolicyAction
    target_fault: str | None = None
    selected_test: str | None = None
    question_for_user: str | None = None
    disagreement_detected: bool = False
    disagreement_reason: str = ""
    reason: str = ""
    prolog_result: PrologResult | None = None
    laya_result: LayaDecisionResult | None = None
    search_trace: SearchTrace | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "target_fault": self.target_fault,
            "selected_test": self.selected_test,
            "question_for_user": self.question_for_user,
            "disagreement_detected": self.disagreement_detected,
            "disagreement_reason": self.disagreement_reason,
            "reason": self.reason,
            "prolog": self.prolog_result.to_dict() if self.prolog_result else None,
            "laya": self.laya_result.to_dict() if self.laya_result else None,
            "search_trace": self.search_trace.to_dict() if self.search_trace else None,
        }


# Mapping of fault names to expected Laya categories
FAULT_CATEGORY_MAP: dict[str, DiagnosticCategory] = {
    "wifi_auth_failure": DiagnosticCategory.WIFI,
    "dhcp_failure": DiagnosticCategory.DHCP,
    "gateway_failure": DiagnosticCategory.GATEWAY,
    "dns_failure": DiagnosticCategory.DNS,
    "wan_failure": DiagnosticCategory.WAN,
    "firewall_blocking": DiagnosticCategory.FIREWALL,
    "proxy_failure": DiagnosticCategory.PROXY,
    "ethernet_link_down": DiagnosticCategory.PHYSICAL_LINK,
}


class DecisionPolicyEngine:
    """Combines Prolog inference, Laya decision signals, search traces, and safety invariants."""

    def __init__(
        self,
        prolog_engine: PrologEngine | None = None,
        laya_engine: LayaEngine | None = None,
        search_engine: DiagnosticSearchEngine | None = None,
    ) -> None:
        self.prolog_engine = prolog_engine or PrologEngine()
        self.laya_engine = laya_engine or LayaEngine()
        self.search_engine = search_engine or DiagnosticSearchEngine(self.prolog_engine)

    def evaluate(
        self,
        state: DiagnosticState,
        user_symptoms: str = "",
        cycle: int = 1,
        max_cycles: int = 8,
    ) -> PolicyDecision:
        """Evaluate current state across all AI components and determine the next policy action."""
        # 1. Check for critical state contradictions or cycle budget exhaustion
        if state.contradictory_predicates():
            return PolicyDecision(
                action=PolicyAction.ASK_USER,
                question_for_user=(
                    f"Conflicting evidence detected on {', '.join(state.contradictory_predicates())}. "
                    "Could you please re-verify your observation?"
                ),
                reason="State contains unresolved conflicting observations from multiple sources.",
            )

        if cycle > max_cycles:
            return PolicyDecision(
                action=PolicyAction.ABSTAIN,
                reason=f"Diagnostic cycle budget exceeded ({max_cycles} cycles) without decisive isolation.",
            )

        # 2. Symbolic Inference via Prolog
        prolog_res = self.prolog_engine.infer(state)

        # Domain topological contradictions (e.g. public IP reached but gateway failed)
        if prolog_res.domain_contradictions:
            return PolicyDecision(
                action=PolicyAction.ESCALATE,
                reason=(
                    f"Domain topological contradiction detected: {', '.join(prolog_res.domain_contradictions)}. "
                    "Requires human network technician inspection."
                ),
                prolog_result=prolog_res,
            )

        # 3. Statistical Decision Modeling via Laya
        laya_res = self.laya_engine.predict(
            state,
            user_symptoms=user_symptoms,
            candidate_hypotheses=prolog_res.candidate_faults,
        )

        # 4. Check for Symbolic-Statistical Disagreement
        disagreement_detected = False
        disagreement_reason = ""

        if len(prolog_res.supported_faults) == 1:
            supported_fault = prolog_res.supported_faults[0]
            expected_cat = FAULT_CATEGORY_MAP.get(supported_fault, DiagnosticCategory.UNKNOWN)
            laya_cat = laya_res.recommended_category

            # Disagreement if Laya strongly points to an orthogonal category
            if expected_cat != DiagnosticCategory.UNKNOWN and laya_cat != DiagnosticCategory.UNKNOWN:
                if laya_cat != expected_cat and laya_res.category_probabilities.get(laya_cat.value, 0) > 0.6:
                    disagreement_detected = True
                    disagreement_reason = (
                        f"Prolog supports '{supported_fault}' ({expected_cat.value}), "
                        f"but Laya decision signal prioritizes '{laya_cat.value}' "
                        f"(prob={laya_res.category_probabilities.get(laya_cat.value, 0):.2f})."
                    )

        # 5. Diagnostic Goal Satisfaction
        if len(prolog_res.supported_faults) == 1:
            final_fault = prolog_res.supported_faults[0]
            if not disagreement_detected:
                return PolicyDecision(
                    action=PolicyAction.DIAGNOSE,
                    target_fault=final_fault,
                    reason=f"Prolog uniquely isolates '{final_fault}' with full supporting evidence.",
                    prolog_result=prolog_res,
                    laya_result=laya_res,
                    disagreement_detected=False,
                )
            # If disagreement was detected, check if additional tests remain for this fault
            next_test, search_trace = self.search_engine.plan_next_action(state, target_fault=final_fault)
            if next_test:
                return PolicyDecision(
                    action=PolicyAction.RUN_TEST,
                    target_fault=final_fault,
                    selected_test=next_test,
                    reason="Symbolic-statistical disagreement requires additional test verification.",
                    prolog_result=prolog_res,
                    laya_result=laya_res,
                    search_trace=search_trace,
                    disagreement_detected=True,
                    disagreement_reason=disagreement_reason,
                )
            # All tests for this fault are verified: accept diagnosis despite prior statistical bias
            return PolicyDecision(
                action=PolicyAction.DIAGNOSE,
                target_fault=final_fault,
                reason=f"Prolog definitively proved '{final_fault}' with verified test evidence.",
                prolog_result=prolog_res,
                laya_result=laya_res,
                disagreement_detected=True,
                disagreement_reason=disagreement_reason,
            )

        # 6. Candidate Exploration via BFS Search & Laya Prioritization
        target_candidate = None
        # Use Laya category to bias search towards matching candidate if present
        for candidate in prolog_res.candidate_faults:
            if FAULT_CATEGORY_MAP.get(candidate) == laya_res.recommended_category:
                target_candidate = candidate
                break

        next_test, search_trace = self.search_engine.plan_next_action(
            state,
            target_fault=target_candidate,
        )

        if next_test:
            return PolicyDecision(
                action=PolicyAction.RUN_TEST,
                selected_test=next_test,
                target_fault=target_candidate or (prolog_res.candidate_faults[0] if prolog_res.candidate_faults else None),
                reason=f"Executing BFS-planned probe '{next_test}' to distinguish active candidate hypotheses.",
                prolog_result=prolog_res,
                laya_result=laya_res,
                search_trace=search_trace,
                disagreement_detected=disagreement_detected,
                disagreement_reason=disagreement_reason,
            )

        # 7. No tests left and no fault supported -> Abstain
        return PolicyDecision(
            action=PolicyAction.ABSTAIN,
            reason="All diagnostic tests completed without reaching a single supported hypothesis.",
            prolog_result=prolog_res,
            laya_result=laya_res,
        )
