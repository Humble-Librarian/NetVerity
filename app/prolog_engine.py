"""Symbolic reasoning engine interfacing with Prolog knowledge base."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .evidence import TruthValue
from .state import DiagnosticState


@dataclass(frozen=True, slots=True)
class RuleFiring:
    """Details of a rule that was triggered during inference."""

    fault: str
    prerequisites: Mapping[str, bool]
    satisfied_evidence: Mapping[str, bool]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fault": self.fault,
            "prerequisites": dict(self.prerequisites),
            "satisfied_evidence": dict(self.satisfied_evidence),
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class PrologResult:
    """Structured result returned from symbolic reasoning."""

    supported_faults: tuple[str, ...] = field(default_factory=tuple)
    candidate_faults: tuple[str, ...] = field(default_factory=tuple)
    eliminated_faults: tuple[str, ...] = field(default_factory=tuple)
    rules_fired: tuple[RuleFiring, ...] = field(default_factory=tuple)
    domain_contradictions: tuple[str, ...] = field(default_factory=tuple)
    engine_mode: str = "EMBEDDED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported_faults": list(self.supported_faults),
            "candidate_faults": list(self.candidate_faults),
            "eliminated_faults": list(self.eliminated_faults),
            "rules_fired": [r.to_dict() for r in self.rules_fired],
            "domain_contradictions": list(self.domain_contradictions),
            "engine_mode": self.engine_mode,
        }


# Canonical rule definitions aligning with prolog/rules.pl
DIAGNOSTIC_RULES: dict[str, dict[str, bool]] = {
    "wifi_auth_failure": {
        "wifi_connected": False,
    },
    "dhcp_failure": {
        "wifi_connected": True,
        "has_valid_ip": False,
    },
    "gateway_failure": {
        "has_valid_ip": True,
        "gateway_reachable": False,
    },
    "dns_failure": {
        "has_valid_ip": True,
        "gateway_reachable": True,
        "internet_ip_reachable": True,
        "dns_resolution_ok": False,
    },
    "wan_failure": {
        "has_valid_ip": True,
        "gateway_reachable": True,
        "internet_ip_reachable": False,
    },
    "packet_loss_failure": {
        "has_valid_ip": True,
        "gateway_reachable": True,
        "packet_loss_high": True,
    },
    "firewall_blocking": {
        "has_valid_ip": True,
        "gateway_reachable": True,
        "firewall_blocking_traffic": True,
    },
    "ip_conflict": {
        "ip_conflict_detected": True,
    },
    "proxy_failure": {
        "internet_ip_reachable": True,
        "proxy_enabled": True,
        "proxy_reachable": False,
    },
    "ethernet_link_down": {
        "ethernet_connected": False,
    },
}

DOMAIN_CONTRADICTIONS: dict[str, dict[str, bool]] = {
    "internet_without_gateway": {
        "gateway_reachable": False,
        "internet_ip_reachable": True,
    },
    "dns_without_ip": {
        "has_valid_ip": False,
        "dns_resolution_ok": True,
    },
    "ip_without_link": {
        "wifi_connected": False,
        "ethernet_connected": False,
        "has_valid_ip": True,
    },
}

RULE_DESCRIPTIONS: dict[str, str] = {
    "wifi_auth_failure": "Device failed to associate or authenticate with the Wi-Fi access point.",
    "dhcp_failure": "Wi-Fi link is active, but device could not obtain a valid IP configuration via DHCP.",
    "gateway_failure": "Valid IP assigned, but default gateway (router) is unreachable.",
    "dns_failure": "Public Internet IP is reachable, but domain name resolution (DNS query) fails.",
    "wan_failure": "Default gateway is reachable, but upstream Internet routing/public IP ping fails.",
    "packet_loss_failure": "Severe packet loss observed across local or upstream hops.",
    "firewall_blocking": "Firewall or security group rules are actively dropping network traffic.",
    "ip_conflict": "Duplicate IP address detected on the local subnet.",
    "proxy_failure": "Internet IP reachable, but configured HTTP/SOCKS proxy is unreachable.",
    "ethernet_link_down": "Physical Ethernet cable disconnected or link negotiation failed.",
}


class PrologEngine:
    """Symbolic reasoning interface supporting SWI-Prolog and embedded Horn-clause inference."""

    def __init__(
        self,
        rules_path: str | Path | None = None,
        swipl_path: str | None = None,
        force_embedded: bool = False,
    ) -> None:
        if rules_path is None:
            rules_path = Path(__file__).resolve().parent.parent / "prolog" / "rules.pl"
        self.rules_path = Path(rules_path)
        self.swipl_path = swipl_path or shutil.which("swipl")
        self.force_embedded = force_embedded

    @property
    def has_swipl(self) -> bool:
        """Check if SWI-Prolog binary is available and executable."""
        if self.force_embedded or not self.swipl_path:
            return False
        try:
            res = subprocess.run(
                [self.swipl_path, "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            return res.returncode == 0
        except Exception:
            return False

    def infer(self, state: DiagnosticState) -> PrologResult:
        """Run symbolic inference over the given DiagnosticState."""
        if self.has_swipl and self.rules_path.exists():
            try:
                return self._infer_swipl(state)
            except Exception:
                # Fall back gracefully to embedded engine if subprocess fails
                pass
        return self._infer_embedded(state)

    def _infer_embedded(self, state: DiagnosticState) -> PrologResult:
        """High-speed pure-Python Horn-clause reasoning."""
        known_facts: dict[str, bool] = {}
        for predicate, truth in state.truths().items():
            if truth is TruthValue.TRUE:
                known_facts[predicate] = True
            elif truth is TruthValue.FALSE:
                known_facts[predicate] = False

        supported_faults: list[str] = []
        candidate_faults: list[str] = []
        eliminated_faults: list[str] = []
        rules_fired: list[RuleFiring] = []
        contradictions: list[str] = []

        # 1. Evaluate fault hypotheses
        for fault, prerequisites in DIAGNOSTIC_RULES.items():
            all_satisfied = True
            is_eliminated = False
            satisfied_evidence: dict[str, bool] = {}

            for pred, required_val in prerequisites.items():
                if pred in known_facts:
                    actual_val = known_facts[pred]
                    if actual_val == required_val:
                        satisfied_evidence[pred] = actual_val
                    else:
                        is_eliminated = True
                        all_satisfied = False
                else:
                    # Unknown fact: not satisfied yet
                    all_satisfied = False

            if all_satisfied:
                supported_faults.append(fault)
                rules_fired.append(
                    RuleFiring(
                        fault=fault,
                        prerequisites=prerequisites,
                        satisfied_evidence=satisfied_evidence,
                        description=RULE_DESCRIPTIONS.get(fault, ""),
                    )
                )
            elif is_eliminated:
                eliminated_faults.append(fault)
            else:
                candidate_faults.append(fault)

        # 2. Check domain topological contradictions
        for contra_name, conditions in DOMAIN_CONTRADICTIONS.items():
            if all(
                pred in known_facts and known_facts[pred] == req_val
                for pred, req_val in conditions.items()
            ):
                contradictions.append(contra_name)

        return PrologResult(
            supported_faults=tuple(supported_faults),
            candidate_faults=tuple(candidate_faults),
            eliminated_faults=tuple(eliminated_faults),
            rules_fired=tuple(rules_fired),
            domain_contradictions=tuple(contradictions),
            engine_mode="EMBEDDED",
        )

    def _infer_swipl(self, state: DiagnosticState) -> PrologResult:
        """Query external SWI-Prolog process via JSON terms."""
        # Convert state into assertz facts
        prolog_facts: list[str] = []
        for predicate, truth in state.truths().items():
            if truth is TruthValue.TRUE:
                prolog_facts.append(f"assertz(fact({predicate}, true))")
            elif truth is TruthValue.FALSE:
                prolog_facts.append(f"assertz(fact({predicate}, false))")

        assert_script = ", ".join(prolog_facts)
        if assert_script:
            assert_script += ", "

        goal = (
            f"consult('{self.rules_path.as_posix()}'), "
            f"{assert_script}"
            "all_supported_faults(Faults), "
            "all_contradictions(Contras), "
            "format('~w|~w', [Faults, Contras]), halt."
        )

        proc = subprocess.run(
            [self.swipl_path or "swipl", "-q", "-g", goal],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )

        output = proc.stdout.strip()
        parts = output.split("|")
        supported_raw = parts[0].strip("[] ").split(",") if len(parts) > 0 else []
        contras_raw = parts[1].strip("[] ").split(",") if len(parts) > 1 else []

        supported = tuple(f.strip() for f in supported_raw if f.strip())
        contradictions = tuple(c.strip() for c in contras_raw if c.strip())

        # Combine with rule introspection
        embedded_ref = self._infer_embedded(state)
        return PrologResult(
            supported_faults=supported,
            candidate_faults=embedded_ref.candidate_faults,
            eliminated_faults=embedded_ref.eliminated_faults,
            rules_fired=embedded_ref.rules_fired,
            domain_contradictions=contradictions,
            engine_mode="SWI_PROLOG",
        )
