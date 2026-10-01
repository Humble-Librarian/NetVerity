"""Tests for Phase 4: Diagnostic Test Simulator and Scenarios."""

from pathlib import Path
import pytest

from app import (
    DiagnosticState,
    DiagnosticTestSimulator,
    EvidenceSource,
    NetworkEnvironment,
    Scenario,
    TruthValue,
)


def test_simulator_returns_evidence_not_diagnosis():
    env = NetworkEnvironment(
        wifi_connected=True,
        has_valid_ip=True,
        gateway_reachable=True,
        internet_ip_reachable=True,
        dns_resolution_ok=False,
    )
    simulator = DiagnosticTestSimulator(env)

    obs = simulator.check_dns(cycle=2)
    assert obs.predicate == "dns_resolution_ok"
    assert obs.value is TruthValue.FALSE
    assert obs.source is EvidenceSource.SIMULATOR
    assert obs.cycle == 2
    # Ensure simulator NEVER returns a diagnosis property
    assert not hasattr(obs, "diagnosis")


def test_simulator_run_test_dispatch():
    env = NetworkEnvironment(has_valid_ip=False)
    simulator = DiagnosticTestSimulator(env)

    results = simulator.run_test("check_ip", cycle=1)
    assert len(results) == 1
    assert results[0].predicate == "has_valid_ip"
    assert results[0].value is TruthValue.FALSE


def test_scenario_loading_and_environment_initialization():
    scenarios_dir = Path(__file__).resolve().parent.parent / "scenarios"
    dns_file = scenarios_dir / "dns_failure.json"

    scenario = Scenario.load_json(dns_file)
    assert scenario.scenario_id == "dns_failure"
    assert scenario.ground_truth_fault == "dns_failure"
    assert scenario.environment.dns_resolution_ok is False
    assert scenario.environment.gateway_reachable is True
