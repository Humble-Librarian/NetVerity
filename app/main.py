"""CLI and demonstration entrypoint for NetVerity diagnostic system."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .agent import HybridDiagnosticAgent
from .explanation import ExplanationEngine
from .laya_engine import LayaEngine
from .policy_engine import DecisionPolicyEngine
from .prolog_engine import PrologEngine
from .search_engine import DiagnosticSearchEngine
from .simulator import Scenario


def run_scenario(scenario_path: Path, verbose: bool = True) -> bool:
    """Execute a single scenario file and print complete diagnostic explanation."""
    if not scenario_path.exists():
        print(f"Error: Scenario file not found at {scenario_path}", file=sys.stderr)
        return False

    scenario = Scenario.load_json(scenario_path)
    print(f"\n============================================================")
    print(f"  RUNNING SCENARIO: {scenario.name.upper()}")
    print(f"  Description: {scenario.description}")
    print(f"  User Symptom: \"{scenario.initial_user_symptoms}\"")
    print(f"============================================================")

    agent = HybridDiagnosticAgent()
    start_time = time.perf_counter()
    result = agent.diagnose_scenario(scenario, verbose=verbose)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    print(result.explanation.format_report())
    print(f"\nDiagnostic Cycles: {result.cycles_completed} | Latency: {elapsed_ms:.2f} ms")
    if scenario.ground_truth_fault:
        status_symbol = "PASSED" if result.success else "FAILED"
        print(f"Ground Truth: {scenario.ground_truth_fault} -> Evaluation: {status_symbol}")
    print("============================================================\n")
    return result.success


def run_evaluation(scenarios_dir: Path) -> None:
    """Batch evaluate all scenarios and output benchmark metrics."""
    scenario_files = sorted(scenarios_dir.glob("*.json"))
    if not scenario_files:
        print(f"No scenarios found in {scenarios_dir}", file=sys.stderr)
        return

    print("\n============================================================")
    print(f"  BATCH BENCHMARK EVALUATION ({len(scenario_files)} SCENARIOS)")
    print("============================================================")

    agent = HybridDiagnosticAgent()
    total = len(scenario_files)
    correct = 0
    latencies: list[float] = []
    cycles_list: list[int] = []

    print(f"{'Scenario ID':<22} | {'Ground Truth':<18} | {'Diagnosis':<18} | {'Cycles':<6} | {'Status'}")
    print("-" * 80)

    for sf in scenario_files:
        scenario = Scenario.load_json(sf)
        t0 = time.perf_counter()
        res = agent.diagnose_scenario(scenario)
        dt = (time.perf_counter() - t0) * 1000
        latencies.append(dt)
        cycles_list.append(res.cycles_completed)

        diag = res.explanation.final_diagnosis
        truth = scenario.ground_truth_fault or "N/A"
        is_pass = res.success
        if is_pass:
            correct += 1

        status_str = "[PASS]" if is_pass else "[FAIL]"
        print(f"{scenario.scenario_id:<22} | {truth:<18} | {diag:<18} | {res.cycles_completed:<6} | {status_str}")

    accuracy = (correct / total) * 100
    avg_latency = sum(latencies) / total
    avg_cycles = sum(cycles_list) / total

    print("-" * 80)
    print(f"Benchmark Summary:")
    print(f"  * Total Scenarios:   {total}")
    print(f"  * Diagnostic Acc:    {accuracy:.1f}% ({correct}/{total})")
    print(f"  * Avg Latency:       {avg_latency:.2f} ms")
    print(f"  * Avg Test Cycles:   {avg_cycles:.1f}")
    print("============================================================\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="NetVerity: Hybrid AI Network Fault Diagnosis Agent")
    parser.add_argument("--demo", type=str, choices=["dns", "dhcp", "gateway", "wifi", "wan", "conflict"], help="Run a demo scenario")
    parser.add_argument("--scenario", type=str, help="Path to a scenario JSON file")
    parser.add_argument("--eval", action="store_true", help="Run batch benchmark evaluation across all scenarios")
    parser.add_argument("--quiet", action="store_true", help="Suppress detailed trace output")

    args = parser.parse_args()
    base_scenarios_dir = Path(__file__).resolve().parent.parent / "scenarios"

    if args.eval:
        run_evaluation(base_scenarios_dir)
    elif args.demo:
        name_map = {
            "dns": "dns_failure.json",
            "dhcp": "dhcp_failure.json",
            "gateway": "gateway_failure.json",
            "wifi": "wifi_failure.json",
            "wan": "wan_failure.json",
            "conflict": "conflict_case.json",
        }
        target_file = base_scenarios_dir / name_map[args.demo]
        run_scenario(target_file, verbose=not args.quiet)
    elif args.scenario:
        scen_path = Path(args.scenario)
        if not scen_path.is_absolute() and not scen_path.exists():
            scen_path = base_scenarios_dir / args.scenario
        run_scenario(scen_path, verbose=not args.quiet)
    else:
        # Default behavior: run DNS demo
        print("No mode specified. Running default DNS demo (use --help for options)...")
        run_scenario(base_scenarios_dir / "dns_failure.json", verbose=True)


if __name__ == "__main__":
    main()
