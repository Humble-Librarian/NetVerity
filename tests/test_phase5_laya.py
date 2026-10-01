"""Tests for Phase 5: Laya decision model adapter and deterministic fallback."""

import pytest

from app import (
    DiagnosticCategory,
    DiagnosticState,
    Evidence,
    EvidenceSource,
    LayaEngine,
)


@pytest.fixture
def laya_engine() -> LayaEngine:
    return LayaEngine(force_mock=True)


def test_laya_category_routing_from_symptoms(laya_engine: LayaEngine):
    state = DiagnosticState()
    symptoms = "I cannot resolve website addresses or domains like google.com"

    res = laya_engine.predict(state, user_symptoms=symptoms, candidate_hypotheses=["dns_failure"])

    assert res.recommended_category is DiagnosticCategory.DNS
    assert res.category_probabilities.get("dns", 0) > 0.25
    assert res.is_mock is True


def test_laya_hypothesis_confidence_evaluation(laya_engine: LayaEngine):
    # State with DNS failed observation
    state = DiagnosticState((Evidence("dns_resolution_ok", False, source=EvidenceSource.SIMULATOR),))
    res = laya_engine.predict(state, user_symptoms="web fails", candidate_hypotheses=["dns_failure", "dhcp_failure"])

    assert res.recommended_category is DiagnosticCategory.DNS
    assert res.hypothesis_confidence.get("dns_failure", 0) >= 0.8
    assert res.urgency_score >= 1.0


def test_laya_serialization_to_dict(laya_engine: LayaEngine):
    state = DiagnosticState()
    res = laya_engine.predict(state, user_symptoms="wifi auth failed")

    data = res.to_dict()
    assert "recommended_category" in data
    assert "urgency_score" in data
    assert "hypothesis_confidence" in data
    assert data["is_mock"] is True
