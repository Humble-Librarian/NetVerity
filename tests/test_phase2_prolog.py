"""Tests for Phase 2: Prolog symbolic inference engine and rules."""

import pytest

from app import (
    DiagnosticState,
    Evidence,
    EvidenceSource,
    PrologEngine,
    TruthValue,
)


@pytest.fixture
def engine() -> PrologEngine:
    return PrologEngine()


def test_empty_state_has_no_supported_faults_and_all_candidates(engine: PrologEngine):
    state = DiagnosticState()
    result = engine.infer(state)

    assert result.supported_faults == ()
    assert "dns_failure" in result.candidate_faults
    assert "dhcp_failure" in result.candidate_faults
    assert "gateway_failure" in result.candidate_faults
    assert result.eliminated_faults == ()
    assert result.domain_contradictions == ()


def test_dns_failure_inference(engine: PrologEngine):
    evidence = (
        Evidence("has_valid_ip", True, source=EvidenceSource.PROBE),
        Evidence("gateway_reachable", True, source=EvidenceSource.PROBE),
        Evidence("internet_ip_reachable", True, source=EvidenceSource.PROBE),
        Evidence("dns_resolution_ok", False, source=EvidenceSource.PROBE),
    )
    state = DiagnosticState(evidence)
    result = engine.infer(state)

    assert result.supported_faults == ("dns_failure",)
    assert len(result.rules_fired) == 1
    firing = result.rules_fired[0]
    assert firing.fault == "dns_failure"
    assert firing.prerequisites == {
        "has_valid_ip": True,
        "gateway_reachable": True,
        "internet_ip_reachable": True,
        "dns_resolution_ok": False,
    }
    assert firing.satisfied_evidence == firing.prerequisites
    assert "dns" in firing.description.lower()


def test_dhcp_failure_inference(engine: PrologEngine):
    evidence = (
        Evidence("wifi_connected", True, source=EvidenceSource.USER),
        Evidence("has_valid_ip", False, source=EvidenceSource.PROBE),
    )
    state = DiagnosticState(evidence)
    result = engine.infer(state)

    assert "dhcp_failure" in result.supported_faults
    assert "gateway_failure" in result.eliminated_faults  # requires has_valid_ip=True


def test_gateway_failure_inference(engine: PrologEngine):
    evidence = (
        Evidence("has_valid_ip", True, source=EvidenceSource.PROBE),
        Evidence("gateway_reachable", False, source=EvidenceSource.PROBE),
    )
    state = DiagnosticState(evidence)
    result = engine.infer(state)

    assert "gateway_failure" in result.supported_faults
    assert "dns_failure" in result.eliminated_faults  # requires gateway_reachable=True


def test_wifi_auth_failure_inference(engine: PrologEngine):
    evidence = (
        Evidence("wifi_connected", False, source=EvidenceSource.USER),
    )
    state = DiagnosticState(evidence)
    result = engine.infer(state)

    assert "wifi_auth_failure" in result.supported_faults
    assert "dhcp_failure" in result.eliminated_faults  # requires wifi_connected=True


def test_wan_failure_inference(engine: PrologEngine):
    evidence = (
        Evidence("has_valid_ip", True, source=EvidenceSource.PROBE),
        Evidence("gateway_reachable", True, source=EvidenceSource.PROBE),
        Evidence("internet_ip_reachable", False, source=EvidenceSource.PROBE),
    )
    state = DiagnosticState(evidence)
    result = engine.infer(state)

    assert "wan_failure" in result.supported_faults
    assert "dns_failure" in result.eliminated_faults  # requires internet_ip_reachable=True


def test_domain_topological_contradiction_detection(engine: PrologEngine):
    # Contradiction: gateway is unreachable, but internet public IP is reachable
    evidence = (
        Evidence("has_valid_ip", True, source=EvidenceSource.PROBE),
        Evidence("gateway_reachable", False, source=EvidenceSource.PROBE),
        Evidence("internet_ip_reachable", True, source=EvidenceSource.SIMULATOR),
    )
    state = DiagnosticState(evidence)
    result = engine.infer(state)

    assert "internet_without_gateway" in result.domain_contradictions


def test_extended_faults_packet_loss_and_firewall(engine: PrologEngine):
    evidence = (
        Evidence("has_valid_ip", True, source=EvidenceSource.PROBE),
        Evidence("gateway_reachable", True, source=EvidenceSource.PROBE),
        Evidence("packet_loss_high", True, source=EvidenceSource.PROBE),
        Evidence("firewall_blocking_traffic", True, source=EvidenceSource.PROBE),
    )
    state = DiagnosticState(evidence)
    result = engine.infer(state)

    assert "packet_loss_failure" in result.supported_faults
    assert "firewall_blocking" in result.supported_faults
