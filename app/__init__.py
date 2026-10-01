"""Evidence, state, and Prolog reasoning foundations for network-fault diagnosis."""

from .evidence import Evidence, EvidenceSource, TruthValue
from .history import DiagnosticEvent, DiagnosticEventKind, DiagnosticHistory
from .prolog_engine import (
    DIAGNOSTIC_RULES,
    DOMAIN_CONTRADICTIONS,
    PrologEngine,
    PrologResult,
    RuleFiring,
)
from .state import DiagnosticState

__all__ = [
    "DIAGNOSTIC_RULES",
    "DOMAIN_CONTRADICTIONS",
    "DiagnosticEvent",
    "DiagnosticEventKind",
    "DiagnosticHistory",
    "DiagnosticState",
    "Evidence",
    "EvidenceSource",
    "PrologEngine",
    "PrologResult",
    "RuleFiring",
    "TruthValue",
]
