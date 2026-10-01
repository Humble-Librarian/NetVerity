"""Hybrid diagnostic agent orchestrating the multi-cycle reasoning loop."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .evidence import Evidence, EvidenceSource, TruthValue
from .explanation import DiagnosticExplanation, ExplanationEngine
from .history import DiagnosticEvent, DiagnosticEventKind, DiagnosticHistory
from .laya_engine import LayaEngine
from .policy_engine import DecisionPolicyEngine, PolicyAction, PolicyDecision
from .prolog_engine import PrologEngine
from .search_engine import DiagnosticSearchEngine, SearchTrace
from .simulator import DiagnosticTestSimulator, Scenario
from .state import DiagnosticState


@dataclass(frozen=True, slots=True)
class DiagnosticSessionResult:
    """The complete, fully-auditable result of a diagnostic session."""

    final_state: DiagnosticState
    final_decision: PolicyDecision
    explanation: DiagnosticExplanation
    history: DiagnosticHistory
    cycles_completed: int
    success: bool
    ground_truth_fault: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "cycles_completed": self.cycles_completed,
            "ground_truth_fault": self.ground_truth_fault,
            "final_diagnosis": self.explanation.final_diagnosis,
            "status": self.explanation.status,
            "final_decision": self.final_decision.to_dict(),
            "explanation": self.explanation.to_dict(),
            "trace": self.history.to_trace(),
        }


class HybridDiagnosticAgent:
    """Orchestrates natural dialogue, symbolic reasoning, statistical modeling, and BFS search."""

    def __init__(
        self,
        prolog_engine: PrologEngine | None = None,
        laya_engine: LayaEngine | None = None,
        search_engine: DiagnosticSearchEngine | None = None,
        policy_engine: DecisionPolicyEngine | None = None,
        explanation_engine: ExplanationEngine | None = None,
    ) -> None:
        self.prolog_engine = prolog_engine or PrologEngine()
        self.laya_engine = laya_engine or LayaEngine()
        self.search_engine = search_engine or DiagnosticSearchEngine(self.prolog_engine)
        self.policy_engine = policy_engine or DecisionPolicyEngine(
            self.prolog_engine, self.laya_engine, self.search_engine
        )
        self.explanation_engine = explanation_engine or ExplanationEngine()

    def diagnose_scenario(
        self,
        scenario: Scenario,
        max_cycles: int = 8,
        verbose: bool = False,
    ) -> DiagnosticSessionResult:
        """Run full autonomous troubleshooting loop on a simulated scenario."""
        simulator = DiagnosticTestSimulator(scenario.environment)
        state = DiagnosticState()
        history = DiagnosticHistory()

        # Check for user-injected contradictions in scenario metadata
        injected = scenario.metadata.get("inject_user_contradiction")
        if injected:
            user_ev = Evidence(
                predicate=injected["predicate"],
                value=injected["value"],
                source=EvidenceSource.USER,
                cycle=0,
            )
            state = state.add_evidence(user_ev)
            history.record_evidence(user_ev, message="User symptom statement")

        cycle = 1
        last_decision: PolicyDecision | None = None
        last_search_trace: SearchTrace | None = None

        while cycle <= max_cycles:
            history.record_cycle(cycle)

            # Evaluate Hybrid Policy
            decision = self.policy_engine.evaluate(
                state=state,
                user_symptoms=scenario.initial_user_symptoms,
                cycle=cycle,
                max_cycles=max_cycles,
            )
            last_decision = decision
            if decision.search_trace:
                last_search_trace = decision.search_trace

            history.record_inference(
                cycle=cycle,
                message=f"Policy decided: {decision.action.value.upper()}",
                metadata=decision.to_dict(),
            )

            if decision.action is PolicyAction.DIAGNOSE:
                break

            if decision.action in (PolicyAction.ABSTAIN, PolicyAction.ESCALATE):
                break

            if decision.action is PolicyAction.RUN_TEST and decision.selected_test:
                # Dispatch test to simulator
                history.record_action(
                    cycle=cycle,
                    message=f"Running diagnostic probe: {decision.selected_test}",
                    metadata={"test": decision.selected_test},
                )
                new_evidence_list = simulator.run_test(decision.selected_test, cycle=cycle)
                for ev in new_evidence_list:
                    state = state.add_evidence(ev)
                    history.record_evidence(ev, cycle=cycle, message=f"Result from {decision.selected_test}")

                cycle += 1
                continue

            if decision.action is PolicyAction.ASK_USER:
                # In automated scenario, record question and break or proceed
                history.record_action(
                    cycle=cycle,
                    message=f"Agent requested user input: {decision.question_for_user}",
                )
                break

            cycle += 1

        assert last_decision is not None
        explanation = self.explanation_engine.generate_explanation(
            state=state,
            final_decision=last_decision,
            history=history,
            search_trace=last_search_trace,
        )

        is_correct = (
            explanation.final_diagnosis == scenario.ground_truth_fault
            if scenario.ground_truth_fault
            else True
        )

        return DiagnosticSessionResult(
            final_state=state,
            final_decision=last_decision,
            explanation=explanation,
            history=history,
            cycles_completed=cycle,
            success=is_correct,
            ground_truth_fault=scenario.ground_truth_fault,
        )
