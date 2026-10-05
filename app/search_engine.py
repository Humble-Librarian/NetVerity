"""Breadth-First Search (BFS) Diagnostic State Planner."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .evidence import Evidence, EvidenceSource, TruthValue
from .prolog_engine import DIAGNOSTIC_RULES, PrologEngine, PrologResult
from .state import DiagnosticState


@dataclass(frozen=True, slots=True)
class SearchNode:
    """A single node in the BFS diagnostic state space."""

    node_id: int
    parent_id: int | None
    action: str | None
    state: DiagnosticState
    depth: int
    hypotheses: tuple[str, ...] = field(default_factory=tuple)
    is_goal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_id": self.parent_id,
            "action": self.action,
            "depth": self.depth,
            "hypotheses": list(self.hypotheses),
            "is_goal": self.is_goal,
            "fingerprint": self.state.fingerprint()[:12],
        }


@dataclass(frozen=True, slots=True)
class SearchTrace:
    """Complete, inspectable record of a BFS diagnostic search exploration."""

    initial_state_fingerprint: str
    goal_reached: bool
    final_path: tuple[str, ...]
    nodes_expanded: int
    search_depth: int
    target_fault: str | None
    nodes: tuple[SearchNode, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_state_fingerprint": self.initial_state_fingerprint,
            "goal_reached": self.goal_reached,
            "final_path": list(self.final_path),
            "nodes_expanded": self.nodes_expanded,
            "search_depth": self.search_depth,
            "target_fault": self.target_fault,
            "nodes": [n.to_dict() for n in self.nodes],
        }

    def format_summary(self) -> str:
        """Academic human-readable summary of the search execution."""
        lines = [
            f"Nodes expanded: {self.nodes_expanded}",
            f"Search depth: {self.search_depth}",
            f"Goal reached: {self.goal_reached}",
        ]
        if self.final_path:
            lines.append("Diagnostic path: " + " -> ".join(self.final_path))
        if self.target_fault:
            lines.append(f"Target hypothesis isolated: {self.target_fault}")
        return "\n".join(lines)


# Mapping of diagnostic actions (tests) to the primary predicates they observe
DIAGNOSTIC_ACTIONS: dict[str, tuple[str, ...]] = {
    "check_wifi": ("wifi_connected",),
    "check_ip": ("has_valid_ip",),
    "check_gateway": ("gateway_reachable",),
    "ping_public_ip": ("internet_ip_reachable",),
    "check_dns": ("dns_resolution_ok",),
    "check_packet_loss": ("packet_loss_high",),
    "check_firewall": ("firewall_blocking_traffic",),
    "check_ip_conflict": ("ip_conflict_detected",),
    "check_proxy": ("proxy_reachable",),
    "check_ethernet": ("ethernet_connected",),
}

# Estimated cost / latency per test for cost-aware prioritization
TEST_COSTS: dict[str, int] = {
    "check_wifi": 1,
    "check_ip": 1,
    "check_gateway": 2,
    "ping_public_ip": 2,
    "check_dns": 2,
    "check_packet_loss": 5,
    "check_firewall": 3,
    "check_ip_conflict": 3,
    "check_proxy": 3,
    "check_ethernet": 1,
}


class DiagnosticSearchEngine:
    """Explicit Breadth-First Search (BFS) planner over diagnostic states."""

    def __init__(self, prolog_engine: PrologEngine | None = None) -> None:
        self.prolog_engine = prolog_engine or PrologEngine()

    def plan_next_action(
        self,
        current_state: DiagnosticState,
        available_actions: Sequence[str] | None = None,
        target_fault: str | None = None,
        max_depth: int = 6,
    ) -> tuple[str | None, SearchTrace]:
        """Run BFS to find the shortest test sequence to reach a supported diagnosis.

        NOTE: This planner expands the BFS tree by simulating assumed test outcomes 
        that align with fault hypotheses, rather than waiting for real observations. 
        It plans against assumed outcomes since it is a planner, not an executor.

        Returns (next_test_to_run, complete_search_trace).
        """
        if available_actions is None:
            # Filter out actions whose predicates are already verified (not UNKNOWN)
            known_truths = current_state.truths()
            available_actions = [
                act
                for act, preds in DIAGNOSTIC_ACTIONS.items()
                if any(known_truths.get(p, TruthValue.UNKNOWN) is TruthValue.UNKNOWN for p in preds)
            ]

        # Check if current state already has a supported diagnosis
        initial_prolog = self.prolog_engine.infer(current_state)
        if len(initial_prolog.supported_faults) == 1 and not initial_prolog.domain_contradictions:
            # Already at goal
            initial_node = SearchNode(
                node_id=0,
                parent_id=None,
                action=None,
                state=current_state,
                depth=0,
                hypotheses=initial_prolog.supported_faults,
                is_goal=True,
            )
            trace = SearchTrace(
                initial_state_fingerprint=current_state.fingerprint(),
                goal_reached=True,
                final_path=(),
                nodes_expanded=1,
                search_depth=0,
                target_fault=initial_prolog.supported_faults[0],
                nodes=(initial_node,),
            )
            return None, trace

        # Determine relevant target faults and required predicates
        candidate_faults = initial_prolog.candidate_faults
        if target_fault and target_fault in candidate_faults:
            relevant_faults = (target_fault,)
        elif candidate_faults:
            relevant_faults = candidate_faults
        else:
            relevant_faults = tuple(DIAGNOSTIC_RULES.keys())

        # Collect unobserved predicates required by relevant faults
        needed_preds: set[str] = set()
        known_truths = current_state.truths()
        for fault in relevant_faults:
            reqs = DIAGNOSTIC_RULES.get(fault, {})
            for pred in reqs:
                if known_truths.get(pred, TruthValue.UNKNOWN) is TruthValue.UNKNOWN:
                    needed_preds.add(pred)

        # Prioritize actions that directly observe needed predicates
        sorted_actions = sorted(
            available_actions,
            key=lambda act: (
                0 if any(p in needed_preds for p in DIAGNOSTIC_ACTIONS.get(act, ())) else 1,
                TEST_COSTS.get(act, 1),
            ),
        )

        # BFS Queue holds: (path_of_actions, current_node_state, parent_node_id, depth)
        queue: deque[tuple[list[str], DiagnosticState, int, int]] = deque()
        visited_fingerprints: set[str] = {current_state.fingerprint()}
        recorded_nodes: list[SearchNode] = []

        root_node = SearchNode(
            node_id=0,
            parent_id=None,
            action=None,
            state=current_state,
            depth=0,
            hypotheses=initial_prolog.supported_faults,
            is_goal=False,
        )
        recorded_nodes.append(root_node)
        queue.append(([], current_state, 0, 0))

        node_counter = 1
        winning_path: list[str] = []
        winning_fault: str | None = None
        nodes_expanded = 0

        while queue:
            path, state, parent_id, depth = queue.popleft()
            nodes_expanded += 1

            if depth >= max_depth:
                continue

            # Generate successors by expanding sorted test actions
            for action in sorted_actions:
                if action in path:
                    continue

                preds = DIAGNOSTIC_ACTIONS.get(action, ())
                # For each relevant hypothesis, simulate the outcome that aligns with the hypothesis rules
                simulated_outcomes: list[dict[str, bool]] = []
                for fault in relevant_faults:
                    reqs = DIAGNOSTIC_RULES.get(fault, {})
                    outcome = {p: reqs[p] for p in preds if p in reqs}
                    if outcome and outcome not in simulated_outcomes:
                        simulated_outcomes.append(outcome)

                if not simulated_outcomes:
                    # Default: simulate true and false for first predicate
                    simulated_outcomes = [{preds[0]: True}, {preds[0]: False}]

                for outcome in simulated_outcomes:
                    new_evidence = [
                        Evidence(
                            predicate=p,
                            value=val,
                            source=EvidenceSource.SIMULATOR,
                            cycle=depth + 1,
                        )
                        for p, val in outcome.items()
                    ]
                    next_state = state.extend(new_evidence)
                    fp = next_state.fingerprint()

                    if fp in visited_fingerprints:
                        continue
                    visited_fingerprints.add(fp)

                    prolog_eval = self.prolog_engine.infer(next_state)
                    is_goal = (
                        len(prolog_eval.supported_faults) == 1
                        and prolog_eval.supported_faults[0] in relevant_faults
                        and not prolog_eval.domain_contradictions
                    )

                    current_node_id = node_counter
                    node_counter += 1

                    node = SearchNode(
                        node_id=current_node_id,
                        parent_id=parent_id,
                        action=action,
                        state=next_state,
                        depth=depth + 1,
                        hypotheses=prolog_eval.supported_faults,
                        is_goal=is_goal,
                    )
                    recorded_nodes.append(node)

                    next_path = path + [action]
                    if is_goal:
                        winning_path = next_path
                        winning_fault = prolog_eval.supported_faults[0]
                        break

                    queue.append((next_path, next_state, current_node_id, depth + 1))

                if winning_path:
                    break

            if winning_path:
                break

        trace = SearchTrace(
            initial_state_fingerprint=current_state.fingerprint(),
            goal_reached=bool(winning_path),
            final_path=tuple(winning_path),
            nodes_expanded=nodes_expanded,
            search_depth=len(winning_path),
            target_fault=winning_fault,
            nodes=tuple(recorded_nodes),
        )

        next_action = winning_path[0] if winning_path else (available_actions[0] if available_actions else None)
        return next_action, trace
