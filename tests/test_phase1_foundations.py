import json
from datetime import UTC, datetime

import pytest

from app import (
    DiagnosticEventKind,
    DiagnosticHistory,
    DiagnosticState,
    Evidence,
    EvidenceSource,
    TruthValue,
)


def test_absence_is_unknown_and_explicit_false_is_false():
    state = DiagnosticState()

    assert state.truth_for("link_up") is TruthValue.UNKNOWN
    assert state.truth_for("missing_predicate") is TruthValue.UNKNOWN

    false_state = state.add_evidence(
        Evidence("link_up", False, source=EvidenceSource.PROBE)
    )
    assert false_state.truth_for("link_up") is TruthValue.FALSE
    assert false_state.truth_for("missing_predicate") is TruthValue.UNKNOWN


def test_same_predicate_true_and_false_are_conflicting_with_provenance():
    observed = Evidence(
        "reachable",
        True,
        source=EvidenceSource.PROBE,
        confidence=0.8,
    )
    contradicted = Evidence(
        "reachable",
        False,
        source=EvidenceSource.USER,
        confidence=0.9,
    )
    state = DiagnosticState((observed, contradicted))

    assert state.truth("reachable") is TruthValue.CONFLICTING
    assert [item.source for item in state.evidence_for("reachable")] == [
        EvidenceSource.PROBE,
        EvidenceSource.USER,
    ]
    assert tuple(state.contradictions) == ("reachable",)
    assert state.contradictions["reachable"] == (observed, contradicted)


def test_canonical_fingerprint_is_stable_across_order_and_metadata_order():
    timestamp = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    first = Evidence(
        "dns_ok",
        True,
        source=EvidenceSource.SYSTEM,
        observed_at=timestamp,
        metadata={"b": 2, "a": ["checked"]},
        confidence=1,
        cycle=2,
    )
    second = Evidence("gateway_ok", False, source=EvidenceSource.POLICY)

    left = DiagnosticState((first, second))
    right = DiagnosticState(
        (
            Evidence("gateway_ok", False, source="policy"),
            Evidence(
                "dns_ok",
                TruthValue.TRUE,
                source="system",
                observation_time=timestamp.isoformat(),
                metadata={"a": ["checked"], "b": 2},
                confidence=1.0,
                cycle=2,
            ),
        )
    )

    assert left.canonical_json() == right.canonical_json()
    assert left.fingerprint() == right.fingerprint()


def test_state_addition_is_copy_on_write():
    original_evidence = Evidence("service_up", True, source=EvidenceSource.SIMULATOR)
    later_evidence = Evidence("service_up", False, source=EvidenceSource.PROBE)
    original = DiagnosticState((original_evidence,))
    updated = original.add_evidence(later_evidence)

    assert original.evidence == (original_evidence,)
    assert original.truth("service_up") is TruthValue.TRUE
    assert updated.evidence == (original_evidence, later_evidence)
    assert updated.truth("service_up") is TruthValue.CONFLICTING
    assert original.fingerprint() != updated.fingerprint()


def test_history_trace_records_cycles_evidence_inferences_and_actions():
    evidence = Evidence(
        "probe_ok",
        True,
        source=EvidenceSource.PROBE,
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
        metadata={"attempt": 1},
        cycle=1,
    )
    history = DiagnosticHistory()
    history.record_cycle(0)
    history.record_evidence(evidence)
    history.record_inference(1, "probe result accepted", {"rule": "probe"})
    history.record_action(1, "schedule follow-up", {"target": "router-a"})

    trace = history.to_trace()
    round_trip = json.loads(history.serialize_trace())

    assert [item["kind"] for item in trace] == [
        DiagnosticEventKind.CYCLE.value,
        DiagnosticEventKind.EVIDENCE_ADDED.value,
        DiagnosticEventKind.INFERENCE.value,
        DiagnosticEventKind.ACTION.value,
    ]
    assert trace[1]["evidence"]["source"] == EvidenceSource.PROBE.value
    assert trace[2]["metadata"] == {"rule": "probe"}
    assert round_trip == trace


def test_invalid_evidence_is_rejected_clearly():
    with pytest.raises(ValueError, match="non-blank"):
        Evidence("   ", True)
    with pytest.raises(ValueError, match="confidence"):
        Evidence("valid", True, confidence=1.1)
    with pytest.raises(TypeError, match="JSON-serializable"):
        Evidence("valid", True, metadata={"bad": object()})
