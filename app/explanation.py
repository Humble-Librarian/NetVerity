"""Contrastive and provenance-aware diagnostic explanation engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .evidence import Evidence, TruthValue
from .history import DiagnosticHistory
from .laya_engine import LayaDecisionResult
from .policy_engine import PolicyDecision
from .prolog_engine import PrologResult
from .search_engine import SearchTrace
from .state import DiagnosticState


@dataclass(frozen=True, slots=True)
class DiagnosticExplanation:
    """Structured, human- and machine-readable explanation of a diagnostic session."""

    final_diagnosis: str
    status: str  # "DIAGNOSED", "ABSTAINED", "ESCALATED", "IN_PROGRESS"
    supporting_evidence: tuple[dict[str, Any], ...]
    eliminated_hypotheses: tuple[dict[str, Any], ...]
    rules_fired: tuple[dict[str, Any], ...]
    laya_recommendation: str
    laya_confidence: float
    search_path: tuple[str, ...]
    nodes_expanded: int
    search_depth: int
    remaining_uncertainty: str
    summary_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_diagnosis": self.final_diagnosis,
            "status": self.status,
            "supporting_evidence": list(self.supporting_evidence),
            "eliminated_hypotheses": list(self.eliminated_hypotheses),
            "rules_fired": list(self.rules_fired),
            "laya_recommendation": self.laya_recommendation,
            "laya_confidence": round(self.laya_confidence, 4),
            "search_path": list(self.search_path),
            "nodes_expanded": self.nodes_expanded,
            "search_depth": self.search_depth,
            "remaining_uncertainty": self.remaining_uncertainty,
            "summary_text": self.summary_text,
        }

    def format_report(self) -> str:
        """Academic human-readable report."""
        lines = [
            "============================================================",
            "                 AI DIAGNOSTIC TRACE REPORT                 ",
            "============================================================",
            f"Final Diagnosis: {self.final_diagnosis.upper() if self.final_diagnosis else 'UNDETERMINED'}",
            f"Diagnostic Status: {self.status}",
            f"Remaining Uncertainty: {self.remaining_uncertainty}",
            "",
            "--- EVIDENCE & PROVENANCE ---",
        ]
        for ev in self.supporting_evidence:
            val_str = "TRUE" if ev["value"] == "true" else ("FALSE" if ev["value"] == "false" else ev["value"])
            lines.append(f"  * {ev['predicate']}: {val_str} (Source: {ev['source']}, Cycle: {ev['cycle']})")

        lines.extend([
            "",
            "--- SYMBOLIC REASONING (PROLOG) ---",
        ])
        for rule in self.rules_fired:
            lines.append(f"  * Rule for [{rule['fault']}]: {rule['description']}")
            lines.append(f"    Prerequisites satisfied: {rule['satisfied_evidence']}")

        if self.eliminated_hypotheses:
            lines.extend([
                "",
                "--- CONTRASTIVE ANALYSIS (ELIMINATED HYPOTHESES) ---",
            ])
            for elim in self.eliminated_hypotheses:
                lines.append(f"  * Ruled out [{elim['fault']}]: {elim['reason']}")

        lines.extend([
            "",
            "--- STATISTICAL DECISION MODEL (LAYA) ---",
            f"  * Category Signal: {self.laya_recommendation}",
            f"  * Target Hypothesis Confidence: {self.laya_confidence:.2%}",
            "",
            "--- SEARCH ENGINE (BFS) ---",
            f"  * Diagnostic Plan Path: {' -> '.join(self.search_path) if self.search_path else 'None (Direct Isolation)'}",
            f"  * Nodes Expanded: {self.nodes_expanded} | Depth: {self.search_depth}",
            "",
            "--- SYNTHESIS & EXPLANATION ---",
            self.summary_text,
            "============================================================",
        ])
        return "\n".join(lines)


class ExplanationEngine:
    """Constructs comprehensive, contrastive explanations across the hybrid pipeline."""

    def generate_explanation(
        self,
        state: DiagnosticState,
        final_decision: PolicyDecision,
        history: DiagnosticHistory | None = None,
        search_trace: SearchTrace | None = None,
    ) -> DiagnosticExplanation:
        """Synthesize facts, Prolog rules, Laya priors, and search traces into an explanation."""
        prolog = final_decision.prolog_result or PrologResult()
        laya = final_decision.laya_result
        search = search_trace or final_decision.search_trace

        diagnosis = final_decision.target_fault or (prolog.supported_faults[0] if prolog.supported_faults else "None")
        status = final_decision.action.value.upper()

        # 1. Compile Supporting Evidence with Provenance
        supporting_evidence = tuple(
            {
                "predicate": ev.predicate,
                "value": ev.value.value,
                "source": ev.source.value,
                "confidence": ev.confidence,
                "cycle": ev.cycle,
            }
            for ev in state.evidence
        )

        # 2. Contrastive Analysis: Why was X diagnosed and not Y?
        eliminated_details: list[dict[str, Any]] = []
        for elim_fault in prolog.eliminated_faults:
            reason = self._explain_elimination(elim_fault, state)
            eliminated_details.append({"fault": elim_fault, "reason": reason})

        # 3. Rules Fired
        rules_fired = tuple(r.to_dict() for r in prolog.rules_fired)

        # 4. Laya Decision Signals
        laya_category = laya.recommended_category.value if laya else "unknown"
        laya_conf = laya.hypothesis_confidence.get(diagnosis, 0.0) if laya else 0.0

        # 5. Search details
        search_path = search.final_path if search else ()
        nodes_expanded = search.nodes_expanded if search else 0
        search_depth = search.search_depth if search else 0

        # 6. Uncertainty level
        if final_decision.disagreement_detected:
            uncertainty = "MEDIUM (Symbolic-Statistical Disagreement Detected)"
        elif status == "DIAGNOSE" and not state.contradictory_predicates():
            uncertainty = "LOW (Uniquely isolated with complete supporting evidence)"
        elif status == "ABSTAIN":
            uncertainty = "HIGH (Inconclusive observations)"
        else:
            uncertainty = "MODERATE"

        # 7. Human-readable contrastive synthesis text
        summary = self._build_natural_explanation(diagnosis, status, state, eliminated_details, final_decision)

        return DiagnosticExplanation(
            final_diagnosis=diagnosis,
            status=status,
            supporting_evidence=supporting_evidence,
            eliminated_hypotheses=tuple(eliminated_details),
            rules_fired=rules_fired,
            laya_recommendation=laya_category,
            laya_confidence=laya_conf,
            search_path=search_path,
            nodes_expanded=nodes_expanded,
            search_depth=search_depth,
            remaining_uncertainty=uncertainty,
            summary_text=summary,
        )

    def _explain_elimination(self, fault: str, state: DiagnosticState) -> str:
        truths = state.truths()
        if fault == "dhcp_failure" and truths.get("has_valid_ip") is TruthValue.TRUE:
            return "A valid IP address was verified, ruling out DHCP lease exhaustion."
        if fault == "gateway_failure" and truths.get("gateway_reachable") is TruthValue.TRUE:
            return "The local default gateway is responsive, ruling out local router failure."
        if fault == "wifi_auth_failure" and truths.get("wifi_connected") is TruthValue.TRUE:
            return "Wi-Fi link association was verified successfully."
        if fault == "wan_failure" and truths.get("internet_ip_reachable") is TruthValue.TRUE:
            return "Public IP (8.8.8.8) is reachable, confirming upstream WAN connectivity."
        if fault == "dns_failure" and truths.get("dns_resolution_ok") is TruthValue.TRUE:
            return "Domain name resolution succeeded."
        return "Prerequisite environmental conditions were not met."

    def _build_natural_explanation(
        self,
        diagnosis: str,
        status: str,
        state: DiagnosticState,
        eliminated: list[dict[str, Any]],
        decision: PolicyDecision,
    ) -> str:
        if status == "DIAGNOSE":
            name = diagnosis.replace("_", " ").title()
            elim_reasons = " ".join([f"{e['fault'].replace('_', ' ').title()} was ruled out because {e['reason'].lower()}" for e in eliminated[:2]])
            return (
                f"The system diagnosed '{name}'. All requisite symbolic constraints were verified without "
                f"contradictions. {elim_reasons}"
            )
        if status == "ABSTAIN":
            return "The diagnostic search could not uniquely isolate a single fault. Additional tests or human technician escalation is recommended."
        if status == "ESCALATE":
            return f"Diagnostic escalation required: {decision.reason}"
        return f"Investigation in progress: {decision.reason}"
