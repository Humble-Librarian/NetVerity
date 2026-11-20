"""Comprehensive leak, immutability, memory, and boundary test suite for Verdixt."""

import gc
import json
import math
import tracemalloc
import weakref
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app import (
    DiagnosticEvent,
    DiagnosticEventKind,
    DiagnosticHistory,
    DiagnosticState,
    Evidence,
    EvidenceSource,
    TruthValue,
)


# =====================================================================
# 1. MUTATION & REFERENCE LEAK TESTS (Tampering / Immutability Leaks)
# =====================================================================

def test_evidence_metadata_mutation_isolation():
    """Verify mutating the input dictionary does not leak into Evidence."""
    input_meta = {"tags": ["critical", "edge"], "nested": {"counter": 42}}
    ev = Evidence("link_down", True, metadata=input_meta)

    # Mutate the source dictionary
    input_meta["tags"].append("mutated")
    input_meta["nested"]["counter"] = 999
    input_meta["new_key"] = "leaked"

    # Evidence metadata must remain untouched
    assert ev.metadata["tags"] == ("critical", "edge")
    assert ev.metadata["nested"]["counter"] == 42
    assert "new_key" not in ev.metadata


def test_evidence_metadata_is_deeply_immutable():
    """Verify Evidence metadata cannot be mutated via item assignment or nested modification."""
    ev = Evidence(
        "link_down",
        True,
        metadata={"tags": ["core"], "config": {"timeout": 30}},
    )

    with pytest.raises(TypeError):
        ev.metadata["tags"] = ("hacked",)  # type: ignore

    with pytest.raises(TypeError):
        ev.metadata["config"]["timeout"] = 99  # type: ignore

    # Nested lists should have frozen to tuples
    assert isinstance(ev.metadata["tags"], tuple)
    with pytest.raises(AttributeError):
        ev.metadata["tags"].append("illegal")  # type: ignore


def test_evidence_to_dict_mutation_does_not_leak_back():
    """Verify mutating the dictionary returned by to_dict() does not leak into Evidence."""
    ev = Evidence("bgp_down", True, metadata={"attempts": 3, "hosts": ["r1", "r2"]})
    exported = ev.to_dict()

    exported["predicate"] = "tampered"
    exported["metadata"]["attempts"] = 100
    exported["metadata"]["hosts"].append("r3")

    assert ev.predicate == "bgp_down"
    assert ev.metadata["attempts"] == 3
    assert ev.metadata["hosts"] == ("r1", "r2")


def test_state_truths_mapping_is_immutable():
    """Verify state.truths() returns an unmodifiable view."""
    ev = Evidence("ospf_ok", True)
    state = DiagnosticState([ev])
    truths = state.truths()

    with pytest.raises(TypeError):
        truths["ospf_ok"] = TruthValue.FALSE  # type: ignore

    with pytest.raises(TypeError):
        truths["injected"] = TruthValue.TRUE  # type: ignore


def test_state_contradictions_mapping_is_immutable():
    """Verify state.contradictions returns an unmodifiable view and cannot be poisoned."""
    ev1 = Evidence("gateway_reachable", True)
    ev2 = Evidence("gateway_reachable", False)
    state = DiagnosticState([ev1, ev2])

    contradictions = state.contradictions
    assert "gateway_reachable" in contradictions

    with pytest.raises(TypeError):
        contradictions["gateway_reachable"] = ()  # type: ignore

    with pytest.raises(TypeError):
        contradictions["injected"] = (ev1,)  # type: ignore


def test_history_trace_mutation_does_not_leak_to_history():
    """Verify mutating history.to_trace() does not alter history internal events."""
    ev = Evidence("packet_drop", True, metadata={"rate": 15})
    history = DiagnosticHistory()
    history.record_evidence(ev, cycle=1, message="initial observation", metadata={"event_tag": "audit"})

    trace = history.to_trace()
    trace[0]["cycle"] = 999
    trace[0]["message"] = "tampered"
    trace[0]["metadata"]["event_tag"] = "hacked"
    trace[0]["evidence"]["metadata"]["rate"] = 9999

    refreshed_trace = history.to_trace()
    assert refreshed_trace[0]["cycle"] == 1
    assert refreshed_trace[0]["message"] == "initial observation"
    assert refreshed_trace[0]["metadata"]["event_tag"] == "audit"
    assert refreshed_trace[0]["evidence"]["metadata"]["rate"] == 15


# =====================================================================
# 2. STATE SPACE & HASHING LEAKS (State Explosion in Search)
# =====================================================================

def test_state_equality_and_hashing_contract_across_insertion_order():
    """CRITICAL: Two states with identical evidence in different insertion orders
    MUST be equal (s1 == s2) and have identical hashes, so search graphs do not
    suffer from state explosion / duplicate memory leaks in sets and dicts.
    """
    e1 = Evidence("dns_ok", True, source=EvidenceSource.SYSTEM)
    e2 = Evidence("ntp_ok", True, source=EvidenceSource.PROBE)
    e3 = Evidence("bgp_ok", False, source=EvidenceSource.ROUTER if hasattr(EvidenceSource, 'ROUTER') else EvidenceSource.USER)

    state_ordered = DiagnosticState([e1, e2, e3])
    state_reversed = DiagnosticState([e3, e2, e1])
    state_shuffled = DiagnosticState([e2, e1, e3])

    # Fingerprints and canonical representations are guaranteed equal
    assert state_ordered.fingerprint() == state_reversed.fingerprint() == state_shuffled.fingerprint()
    assert hash(state_ordered) == hash(state_reversed) == hash(state_shuffled)

    # State equality must hold
    assert state_ordered == state_reversed
    assert state_ordered == state_shuffled
    assert state_reversed == state_shuffled

    # Set inclusion / deduplication test: search graph visited set
    visited = {state_ordered}
    assert state_reversed in visited, "State reversed must be recognized in visited set!"
    assert state_shuffled in visited, "State shuffled must be recognized in visited set!"
    assert len(visited) == 1, "Duplicate states must not leak into visited set!"


def test_diagnostic_event_hashability_and_set_membership():
    """CRITICAL: DiagnosticEvent must be hashable and storable in sets/dicts.
    Currently, frozen dataclass with mappingproxy causes TypeError: unhashable type: 'dict'.
    """
    ev = Evidence("link_down", True)
    event1 = DiagnosticEvent(1, DiagnosticEventKind.EVIDENCE_ADDED, evidence=ev, metadata={"attempt": 1})
    event2 = DiagnosticEvent(1, DiagnosticEventKind.EVIDENCE_ADDED, evidence=ev, metadata={"attempt": 1})

    # Hashing should not raise TypeError
    try:
        h1 = hash(event1)
        h2 = hash(event2)
        assert h1 == h2
        event_set = {event1}
        assert event2 in event_set
        assert len(event_set) == 1
    except TypeError as exc:
        pytest.fail(f"DiagnosticEvent is not hashable: {exc}")


def test_state_inequality_with_different_evidence():
    """States with distinct evidence must not compare equal."""
    e1 = Evidence("p1", True)
    e2 = Evidence("p2", True)
    s1 = DiagnosticState([e1])
    s2 = DiagnosticState([e2])
    assert s1 != s2
    assert s1 != "not_a_state"
    assert s1 != 42


# =====================================================================
# 3. MEMORY LEAKS & RESOURCE ALLOCATION
# =====================================================================

def test_state_garbage_collection_and_no_circular_references():
    """Verify that discarded DiagnosticState objects are properly garbage collected."""
    e = Evidence("mem_test", True)
    state = DiagnosticState([e])

    weak_ref = weakref.ref(state)
    assert weak_ref() is not None

    del state
    gc.collect()

    assert weak_ref() is None, "DiagnosticState leaked or retained by circular references!"


def test_copy_on_write_memory_scaling():
    """Verify that successive state.add_evidence calls do not exhibit runaway memory leaks."""
    tracemalloc.start()
    gc.collect()
    snapshot_before = tracemalloc.take_snapshot()

    current_state = DiagnosticState()
    for i in range(200):
        ev = Evidence(f"metric_{i % 20}", True, cycle=i, metadata={"idx": i})
        current_state = current_state.add_evidence(ev)

    gc.collect()
    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snapshot_after.compare_to(snapshot_before, "lineno")
    total_diff_kb = sum(stat.size_diff for stat in stats) / 1024

    # 200 state transitions should use only modest memory (less than 2 MB total diff)
    assert total_diff_kb < 2048, f"Suspicious memory growth: {total_diff_kb:.2f} KB"
    assert len(current_state.evidence) == 200


def test_history_weakref_cleanup():
    """Verify DiagnosticHistory is cleaned up when dereferenced."""
    history = DiagnosticHistory()
    for i in range(10):
        history.record_cycle(i)
    weak_hist = weakref.ref(history)
    del history
    gc.collect()
    assert weak_hist() is None


# =====================================================================
# 4. EXCEPTION LEAKS & VALIDATION BOUNDARIES
# =====================================================================

def test_diagnostic_event_cycle_none_validation():
    """DiagnosticEvent must raise TypeError/ValueError for cycle=None, NOT AssertionError."""
    with pytest.raises((TypeError, ValueError)) as excinfo:
        DiagnosticEvent(cycle=None)  # type: ignore
    assert not issubclass(excinfo.type, AssertionError), "Must not raise raw AssertionError"


def test_diagnostic_event_negative_cycle():
    """DiagnosticEvent must reject negative cycles."""
    with pytest.raises(ValueError):
        DiagnosticEvent(cycle=-1)


def test_evidence_confidence_boundary_leak():
    """Confidence must strictly lie in [0.0, 1.0] and reject NaN, Inf, and booleans."""
    # Valid boundaries
    assert Evidence("test", True, confidence=0.0).confidence == 0.0
    assert Evidence("test", True, confidence=1.0).confidence == 1.0
    assert Evidence("test", True, confidence=0).confidence == 0.0
    assert Evidence("test", True, confidence=1).confidence == 1.0

    # Invalid: booleans disguised as ints
    with pytest.raises(TypeError, match="confidence"):
        Evidence("test", True, confidence=True)  # type: ignore
    with pytest.raises(TypeError, match="confidence"):
        Evidence("test", True, confidence=False)  # type: ignore

    # Invalid: out of bounds
    with pytest.raises(ValueError, match="confidence"):
        Evidence("test", True, confidence=-0.0001)
    with pytest.raises(ValueError, match="confidence"):
        Evidence("test", True, confidence=1.0001)

    # Invalid: non-finite
    with pytest.raises(ValueError, match="confidence"):
        Evidence("test", True, confidence=float("nan"))
    with pytest.raises(ValueError, match="confidence"):
        Evidence("test", True, confidence=float("inf"))
    with pytest.raises(ValueError, match="confidence"):
        Evidence("test", True, confidence=float("-inf"))


def test_evidence_metadata_non_finite_floats_rejected():
    """Metadata must reject non-finite float values to prevent JSON corruption."""
    with pytest.raises(ValueError, match="non-finite float"):
        Evidence("test", True, metadata={"metric": float("nan")})
    with pytest.raises(ValueError, match="non-finite float"):
        Evidence("test", True, metadata={"metric": float("inf")})


def test_evidence_cycle_validation():
    """Evidence cycle must be non-negative int or None, rejecting booleans and negatives."""
    assert Evidence("test", True, cycle=0).cycle == 0
    assert Evidence("test", True, cycle=None).cycle is None

    with pytest.raises(ValueError):
        Evidence("test", True, cycle=-1)
    with pytest.raises(ValueError):
        Evidence("test", True, cycle=True)  # type: ignore
    with pytest.raises(ValueError):
        Evidence("test", True, cycle="1")  # type: ignore


def test_predicate_whitespace_and_blank_handling():
    """Predicate strings must be stripped and non-blank."""
    ev = Evidence("  bgp_neighbor_established  ", True)
    assert ev.predicate == "bgp_neighbor_established"

    with pytest.raises(ValueError, match="non-blank string"):
        Evidence("   \t\n  ", True)
    with pytest.raises(TypeError, match="non-blank string"):
        Evidence(None, True)  # type: ignore
    with pytest.raises(TypeError, match="non-blank string"):
        Evidence(12345, True)  # type: ignore


def test_observation_time_timezone_parity():
    """Datetime with timezone offset and UTC ISO strings must normalize to identical UTC microseconds."""
    dt_local = datetime(2026, 6, 1, 10, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    iso_utc = "2026-06-01T05:00:00Z"

    e1 = Evidence("sync_ok", True, observed_at=dt_local)
    e2 = Evidence("sync_ok", True, observation_time=iso_utc)

    assert e1.observed_at == e2.observed_at
    assert e1.canonical_json() == e2.canonical_json()
    assert e1.fingerprint == e2.fingerprint


# =====================================================================
# 5. TRUTH DERIVATION & CONTRADICTION PARITY
# =====================================================================

def test_truth_derivation_unknown_resolution():
    """State with explicit UNKNOWN evidence derives to UNKNOWN unless overridden by definite truth."""
    e_unknown = Evidence("route_active", TruthValue.UNKNOWN)
    s_only_unknown = DiagnosticState([e_unknown])
    assert s_only_unknown.truth_for("route_active") is TruthValue.UNKNOWN

    # Adding TRUE overrides UNKNOWN
    e_true = Evidence("route_active", TruthValue.TRUE)
    s_true = s_only_unknown.add_evidence(e_true)
    assert s_true.truth_for("route_active") is TruthValue.TRUE

    # Adding FALSE alongside TRUE causes CONFLICTING
    e_false = Evidence("route_active", TruthValue.FALSE)
    s_conflict = s_true.add_evidence(e_false)
    assert s_conflict.truth_for("route_active") is TruthValue.CONFLICTING
    assert "route_active" in s_conflict.contradictions


def test_state_extend_with_iterable_and_generator():
    """state.extend must handle generators and lists cleanly."""
    def gen_evidence():
        yield Evidence("p1", True)
        yield Evidence("p2", False)

    state = DiagnosticState().extend(gen_evidence())
    assert state.truth_for("p1") is TruthValue.TRUE
    assert state.truth_for("p2") is TruthValue.FALSE
    assert len(state.evidence) == 2


def test_circular_metadata_rejection():
    """Circular mappings must be caught cleanly as ValueError rather than RecursionError."""
    d = {}
    d["self"] = d
    with pytest.raises(ValueError, match="circular reference"):
        Evidence("test", True, metadata=d)


def test_diagnostic_event_and_evidence_weakref_support():
    """DiagnosticEvent and Evidence must support weakref for interning and memory caches."""
    ev = Evidence("p", True)
    w_ev = weakref.ref(ev)
    assert w_ev() is ev

    event = DiagnosticEvent(0, evidence=ev)
    w_event = weakref.ref(event)
    assert w_event() is event

