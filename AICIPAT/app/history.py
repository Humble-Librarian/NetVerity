"""Serializable diagnostic event and history primitives."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Any

from .evidence import (
    Evidence,
    JSONValue,
    _normalise_cycle,
    _normalise_metadata,
    _thaw_json,
)


class DiagnosticEventKind(str, Enum):
    """Kinds of facts recorded in a diagnosis trace."""

    CYCLE = "cycle"
    EVIDENCE_ADDED = "evidence_added"
    INFERENCE = "inference"
    ACTION = "action"


def _normalise_kind(kind: DiagnosticEventKind | str) -> DiagnosticEventKind:
    if isinstance(kind, DiagnosticEventKind):
        return kind
    if isinstance(kind, str):
        candidate = kind.strip().lower()
        try:
            return DiagnosticEventKind(candidate)
        except ValueError:
            try:
                return DiagnosticEventKind[candidate.upper()]
            except KeyError as error:
                raise ValueError(
                    "kind must be cycle, evidence_added, inference, or action"
                ) from error
    raise TypeError("kind must be a DiagnosticEventKind or event-kind string")


@dataclass(frozen=True, slots=True, init=False)
class DiagnosticEvent:
    """One serializable step in a diagnostic history."""

    cycle: int
    kind: DiagnosticEventKind
    evidence: Evidence | None
    message: str | None
    metadata: Mapping[str, Any]

    def __init__(
        self,
        cycle: int,
        kind: DiagnosticEventKind | str = DiagnosticEventKind.CYCLE,
        evidence: Evidence | None = None,
        message: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        *,
        event_type: DiagnosticEventKind | str | None = None,
        description: str | None = None,
        details: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        initial_kind = _normalise_kind(kind)
        if event_type is not None:
            requested_kind = _normalise_kind(event_type)
            if initial_kind is not DiagnosticEventKind.CYCLE and initial_kind is not requested_kind:
                raise ValueError("kind and event_type disagree")
            kind = requested_kind
        if description is not None:
            if message is not None and message != description:
                raise ValueError("message and description disagree")
            message = description
        aliases = [item for item in (details, data) if item is not None]
        if aliases:
            if metadata is not None and any(metadata != item for item in aliases):
                raise ValueError("metadata and details/data disagree")
            if len(aliases) == 2 and aliases[0] != aliases[1]:
                raise ValueError("details and data disagree")
            metadata = aliases[0]

        normalised_cycle = _normalise_cycle(cycle)
        assert normalised_cycle is not None
        if not isinstance(evidence, (Evidence, type(None))):
            raise TypeError("event evidence must be an Evidence instance or None")
        if message is not None and not isinstance(message, str):
            raise TypeError("event message must be a string or None")

        object.__setattr__(self, "cycle", normalised_cycle)
        object.__setattr__(self, "kind", _normalise_kind(kind))
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "metadata", _normalise_metadata(metadata))

    @property
    def event_type(self) -> DiagnosticEventKind:
        return self.kind

    @property
    def description(self) -> str | None:
        return self.message

    @property
    def details(self) -> Mapping[str, Any]:
        return self.metadata

    @classmethod
    def cycle_started(
        cls, cycle: int, metadata: Mapping[str, Any] | None = None
    ) -> DiagnosticEvent:
        return cls(cycle=cycle, kind=DiagnosticEventKind.CYCLE, metadata=metadata)

    @classmethod
    def evidence_added(
        cls,
        evidence: Evidence,
        *,
        cycle: int | None = None,
        message: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> DiagnosticEvent:
        if not isinstance(evidence, Evidence):
            raise TypeError("evidence must be an Evidence instance")
        event_cycle = evidence.cycle if cycle is None else cycle
        if event_cycle is None:
            event_cycle = 0
        return cls(
            cycle=event_cycle,
            kind=DiagnosticEventKind.EVIDENCE_ADDED,
            evidence=evidence,
            message=message,
            metadata=metadata,
        )

    @classmethod
    def inference(
        cls,
        cycle: int,
        message: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> DiagnosticEvent:
        return cls(
            cycle=cycle,
            kind=DiagnosticEventKind.INFERENCE,
            message=message,
            metadata=metadata,
        )

    @classmethod
    def action(
        cls,
        cycle: int,
        message: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> DiagnosticEvent:
        return cls(
            cycle=cycle,
            kind=DiagnosticEventKind.ACTION,
            message=message,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "cycle": self.cycle,
            "kind": self.kind.value,
            "evidence": self.evidence.to_dict() if self.evidence is not None else None,
            "message": self.message,
            "metadata": _thaw_json(self.metadata),
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def fingerprint(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


class DiagnosticHistory:
    """An append-only, serializable collection of diagnostic events."""

    def __init__(self, events: Iterable[DiagnosticEvent] = ()) -> None:
        self._events: list[DiagnosticEvent] = []
        for event in events:
            self.record(event)

    @property
    def events(self) -> tuple[DiagnosticEvent, ...]:
        return tuple(self._events)

    def record(self, event: DiagnosticEvent) -> DiagnosticEvent:
        if not isinstance(event, DiagnosticEvent):
            raise TypeError("event must be a DiagnosticEvent instance")
        self._events.append(event)
        return event

    add_event = record

    def record_cycle(
        self, cycle: int, metadata: Mapping[str, Any] | None = None
    ) -> DiagnosticEvent:
        return self.record(DiagnosticEvent.cycle_started(cycle, metadata))

    def record_evidence(
        self,
        evidence: Evidence,
        *,
        cycle: int | None = None,
        message: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> DiagnosticEvent:
        return self.record(
            DiagnosticEvent.evidence_added(
                evidence,
                cycle=cycle,
                message=message,
                metadata=metadata,
            )
        )

    def record_inference(
        self,
        cycle: int,
        message: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> DiagnosticEvent:
        return self.record(DiagnosticEvent.inference(cycle, message, metadata))

    def record_action(
        self,
        cycle: int,
        message: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> DiagnosticEvent:
        return self.record(DiagnosticEvent.action(cycle, message, metadata))

    def copy(self) -> DiagnosticHistory:
        return type(self)(self._events)

    def to_trace(self) -> list[dict[str, JSONValue]]:
        """Return a fresh JSON-compatible trace."""

        return [event.to_dict() for event in self._events]

    trace = to_trace

    def serialize_trace(self) -> str:
        return json.dumps(
            self.to_trace(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self):
        return iter(self.events)
