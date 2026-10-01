"""Immutable diagnostic state and four-valued truth derivation."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from types import MappingProxyType
from typing import Any

from .evidence import Evidence, TruthValue


class _ContradictionView(Mapping[str, tuple[Evidence, ...]]):
    """Read-only contradiction mapping that is also callable for convenience."""

    def __init__(self, values: Mapping[str, tuple[Evidence, ...]]) -> None:
        self._values = MappingProxyType(dict(values))

    def __getitem__(self, key: str) -> tuple[Evidence, ...]:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __call__(self) -> Mapping[str, tuple[Evidence, ...]]:
        """Return this read-only view, supporting ``state.contradictions()``."""

        return self


def _predicate_name(predicate: str) -> str:
    if not isinstance(predicate, str):
        raise TypeError("predicate must be a non-blank string")
    predicate = predicate.strip()
    if not predicate:
        raise ValueError("predicate must be a non-blank string")
    return predicate


@dataclass(frozen=True, slots=True, init=False)
class DiagnosticState:
    """A copy-on-write collection of observed evidence.

    Absence is represented by no observations and derives to UNKNOWN.  Adding
    an observation always returns a new state; existing states and their
    evidence tuples remain unchanged.
    """

    _evidence: tuple[Evidence, ...] = field(default_factory=tuple, repr=False)

    def __init__(self, evidence: Iterable[Evidence] = ()) -> None:
        if isinstance(evidence, Evidence):
            evidence = (evidence,)
        try:
            copied = tuple(evidence)
        except TypeError as error:
            raise TypeError("evidence must be an iterable of Evidence objects") from error
        if any(not isinstance(item, Evidence) for item in copied):
            raise TypeError("evidence must contain only Evidence objects")
        object.__setattr__(self, "_evidence", copied)

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        """All observations in insertion order, including their provenance."""

        return self._evidence

    @property
    def observed_evidence(self) -> tuple[Evidence, ...]:
        return self._evidence

    def add_evidence(self, evidence: Evidence) -> DiagnosticState:
        """Return a new state containing ``evidence``."""

        if not isinstance(evidence, Evidence):
            raise TypeError("evidence must be an Evidence instance")
        return type(self)(self._evidence + (evidence,))

    def extend(self, evidence: Iterable[Evidence]) -> DiagnosticState:
        """Return a new state containing all supplied observations."""

        return type(self)(self._evidence + tuple(evidence))

    def evidence_for(self, predicate: str) -> tuple[Evidence, ...]:
        predicate = _predicate_name(predicate)
        return tuple(item for item in self._evidence if item.predicate == predicate)

    def truth_for(self, predicate: str) -> TruthValue:
        """Derive a predicate truth without treating absence as FALSE."""

        observations = self.evidence_for(predicate)
        if not observations:
            return TruthValue.UNKNOWN

        values = {item.value for item in observations}
        if TruthValue.CONFLICTING in values:
            return TruthValue.CONFLICTING
        if TruthValue.TRUE in values and TruthValue.FALSE in values:
            return TruthValue.CONFLICTING
        if TruthValue.TRUE in values:
            return TruthValue.TRUE
        if TruthValue.FALSE in values:
            return TruthValue.FALSE
        return TruthValue.UNKNOWN

    # Short aliases make the state pleasant to use from later search code.
    truth = truth_for
    derive_truth = truth_for

    def truths(self) -> Mapping[str, TruthValue]:
        """Return derived truths for predicates that have observations."""

        predicates = sorted({item.predicate for item in self._evidence})
        return MappingProxyType({predicate: self.truth_for(predicate) for predicate in predicates})

    @property
    def contradictions(self) -> Mapping[str, tuple[Evidence, ...]]:
        """Evidence grouped by every predicate whose truth is CONFLICTING."""

        values = {
            predicate: self.evidence_for(predicate)
            for predicate, truth in self.truths().items()
            if truth is TruthValue.CONFLICTING
        }
        return _ContradictionView(values)

    def contradictory_predicates(self) -> tuple[str, ...]:
        return tuple(self.contradictions)

    def canonical(self) -> tuple[dict[str, Any], ...]:
        """Return observations in a stable order independent of insertion order."""

        ordered = sorted(self._evidence, key=lambda item: item.canonical_json())
        return tuple(item.canonical() for item in ordered)

    @property
    def canonical_form(self) -> tuple[dict[str, Any], ...]:
        return self.canonical()

    def canonical_json(self) -> str:
        return json.dumps(
            list(self.canonical()),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def fingerprint(self) -> str:
        """Return a deterministic SHA-256 identity for search bookkeeping."""

        return sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @property
    def fingerprint_value(self) -> str:
        return self.fingerprint()

    def __hash__(self) -> int:
        return hash(self.fingerprint())
