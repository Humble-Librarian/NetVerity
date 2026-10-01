"""End-to-End Integration and Benchmark Tests across all Fault Scenarios."""

from pathlib import Path
import pytest

from app import (
    HybridDiagnosticAgent,
    PolicyAction,
    Scenario,
)

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


@pytest.fixture
def agent() -> HybridDiagnosticAgent:
    return HybridDiagnosticAgent()


def test_end_to_end_dns_failure(agent: HybridDiagnosticAgent):
    scenario = Scenario.load_json(SCENARIOS_DIR / "dns_failure.json")
    result = agent.diagnose_scenario(scenario)

    assert result.success is True
    assert result.explanation.final_diagnosis == "dns_failure"
    assert result.explanation.status == "DIAGNOSE"
    assert result.cycles_completed >= 1
    assert "dns_resolution_ok" in [ev["predicate"] for ev in result.explanation.supporting_evidence]
    # Check that explanation text is generated
    report = result.explanation.format_report()
    assert "DNS" in report


def test_end_to_end_dhcp_failure(agent: HybridDiagnosticAgent):
    scenario = Scenario.load_json(SCENARIOS_DIR / "dhcp_failure.json")
    result = agent.diagnose_scenario(scenario)

    assert result.success is True
    assert result.explanation.final_diagnosis == "dhcp_failure"
    assert result.explanation.status == "DIAGNOSE"


def test_end_to_end_gateway_failure(agent: HybridDiagnosticAgent):
    scenario = Scenario.load_json(SCENARIOS_DIR / "gateway_failure.json")
    result = agent.diagnose_scenario(scenario)

    assert result.success is True
    assert result.explanation.final_diagnosis == "gateway_failure"
    assert result.explanation.status == "DIAGNOSE"


def test_end_to_end_wifi_failure(agent: HybridDiagnosticAgent):
    scenario = Scenario.load_json(SCENARIOS_DIR / "wifi_failure.json")
    result = agent.diagnose_scenario(scenario)

    assert result.success is True
    assert result.explanation.final_diagnosis == "wifi_auth_failure"
    assert result.explanation.status == "DIAGNOSE"


def test_end_to_end_wan_failure(agent: HybridDiagnosticAgent):
    scenario = Scenario.load_json(SCENARIOS_DIR / "wan_failure.json")
    result = agent.diagnose_scenario(scenario)

    assert result.success is True
    assert result.explanation.final_diagnosis == "wan_failure"
    assert result.explanation.status == "DIAGNOSE"


def test_end_to_end_conflict_case(agent: HybridDiagnosticAgent):
    scenario = Scenario.load_json(SCENARIOS_DIR / "conflict_case.json")
    result = agent.diagnose_scenario(scenario)

    # Contradiction scenario should be handled cleanly without crashing
    assert result.final_decision is not None
    assert result.cycles_completed >= 1
