"""Tests for Phase 3: Explicit BFS Diagnostic Search Planner."""

import pytest

from app import (
    DiagnosticSearchEngine,
    DiagnosticState,
    Evidence,
    EvidenceSource,
    PrologEngine,
    SearchTrace,
)


@pytest.fixture
def search_engine() -> DiagnosticSearchEngine:
    return DiagnosticSearchEngine()


def test_bfs_finds_path_to_dns_failure(search_engine: DiagnosticSearchEngine):
    # Initial state: has IP, gateway ok, public IP ok
    evidence = (
        Evidence("has_valid_ip", True, source=EvidenceSource.PROBE),
        Evidence("gateway_reachable", True, source=EvidenceSource.PROBE),
        Evidence("internet_ip_reachable", True, source=EvidenceSource.PROBE),
    )
    state = DiagnosticState(evidence)

    next_act, trace = search_engine.plan_next_action(state, target_fault="dns_failure")

    assert next_act == "check_dns"
    assert trace.goal_reached is True
    assert "check_dns" in trace.final_path
    assert trace.target_fault == "dns_failure"
    assert trace.nodes_expanded >= 1
    assert trace.search_depth >= 1


def test_bfs_on_already_isolated_state_returns_none_action(search_engine: DiagnosticSearchEngine):
    # State with all facts already isolating dhcp_failure
    evidence = (
        Evidence("wifi_connected", True, source=EvidenceSource.USER),
        Evidence("has_valid_ip", False, source=EvidenceSource.SIMULATOR),
    )
    state = DiagnosticState(evidence)

    next_act, trace = search_engine.plan_next_action(state)

    assert next_act is None
    assert trace.goal_reached is True
    assert trace.search_depth == 0
    assert trace.target_fault == "dhcp_failure"


def test_search_trace_serialization_and_summary(search_engine: DiagnosticSearchEngine):
    state = DiagnosticState()
    next_act, trace = search_engine.plan_next_action(state)

    trace_dict = trace.to_dict()
    assert "initial_state_fingerprint" in trace_dict
    assert "nodes" in trace_dict
    assert isinstance(trace_dict["nodes"], list)
    assert len(trace_dict["nodes"]) > 0

    summary = trace.format_summary()
    assert "Nodes expanded:" in summary
    assert "Search depth:" in summary
