"""Tests for Phase 6: Hybrid Decision Policy Engine."""

import pytest

from app import (
    DecisionPolicyEngine,
    DiagnosticState,
    Evidence,
    EvidenceSource,
    PolicyAction,
)


@pytest.fixture
def policy_engine() -> DecisionPolicyEngine:
    return DecisionPolicyEngine()


def test_policy_decides_diagnose_when_fault_is_uniquely_supported(policy_engine: DecisionPolicyEngine):
    # State with verified DNS failure
    evidence = (
        Evidence("has_valid_ip", True, source=EvidenceSource.PROBE),
        Evidence("gateway_reachable", True, source=EvidenceSource.PROBE),
        Evidence("internet_ip_reachable", True, source=EvidenceSource.PROBE),
        Evidence("dns_resolution_ok", False, source=EvidenceSource.PROBE),
    )
    state = DiagnosticState(evidence)

    decision = policy_engine.evaluate(state, user_symptoms="domain resolution failed")

    assert decision.action is PolicyAction.DIAGNOSE
    assert decision.target_fault == "dns_failure"
    assert decision.disagreement_detected is False


def test_policy_decides_run_test_when_evidence_is_partial(policy_engine: DecisionPolicyEngine):
    # Initial symptom: wifi ok, but websites fail
    evidence = (Evidence("wifi_connected", True, source=EvidenceSource.USER),)
    state = DiagnosticState(evidence)

    decision = policy_engine.evaluate(state, user_symptoms="connected to wifi but nothing opens")

    assert decision.action is PolicyAction.RUN_TEST
    assert decision.selected_test is not None
    assert decision.search_trace is not None


def test_policy_detects_contradictions_and_asks_user(policy_engine: DecisionPolicyEngine):
    # Contradictory evidence on gateway_reachable
    evidence = (
        Evidence("gateway_reachable", True, source=EvidenceSource.PROBE),
        Evidence("gateway_reachable", False, source=EvidenceSource.USER),
    )
    state = DiagnosticState(evidence)

    decision = policy_engine.evaluate(state)

    assert decision.action is PolicyAction.ASK_USER
    assert decision.question_for_user is not None
    assert "gateway_reachable" in decision.question_for_user


def test_policy_escalates_on_domain_topological_contradiction(policy_engine: DecisionPolicyEngine):
    # Public IP reachable, but local gateway unreachable
    evidence = (
        Evidence("has_valid_ip", True, source=EvidenceSource.PROBE),
        Evidence("gateway_reachable", False, source=EvidenceSource.PROBE),
        Evidence("internet_ip_reachable", True, source=EvidenceSource.PROBE),
    )
    state = DiagnosticState(evidence)

    decision = policy_engine.evaluate(state)

    assert decision.action is PolicyAction.ESCALATE
    assert "domain topological contradiction" in decision.reason.lower()
