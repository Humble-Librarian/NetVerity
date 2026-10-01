"""Evidence primitives used by the diagnosis state."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from types import MappingProxyType
from typing import Any, TypeAlias


JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class TruthValue(str, Enum):
    """The four-valued truth domain used by diagnostic observations."""

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"


class EvidenceSource(str, Enum):
    """Where an observation or assertion originated."""

    SIMULATOR = "simulator"
    USER = "user"
    PROBE = "probe"
    PROLOG = "prolog"
    LAYA = "laya"
    POLICY = "policy"
    SYSTEM = "system"


def _normalise_json(value: Any, *, path: str = "metadata") -> JSONValue:
    """Validate and copy a JSON-compatible value."""

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite float")
        return value
    if isinstance(value, Mapping):
        copied: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} has a non-string key: {key!r}")
            copied[key] = _normalise_json(item, path=f"{path}.{key}")
        return copied
    if isinstance(value, (list, tuple)):
        return [
            _normalise_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(
        f"{path} must contain only JSON-serializable values; "
        f"got {type(value).__name__}"
    )


def _freeze_json(value: JSONValue) -> JSONValue:
    """Convert a validated JSON value into recursively immutable containers."""

    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze_json(item) for key, item in value.items()}  # type: ignore[return-value]
        )  # type: ignore[return-value]
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)  # type: ignore[return-value]
    return value


def _thaw_json(value: Any) -> JSONValue:
    """Return a fresh, ordinary JSON value from an immutable JSON value."""

    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _normalise_metadata(metadata: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, Mapping):
        raise TypeError(
            "metadata must be a mapping containing only JSON-serializable values"
        )
    normalised = _normalise_json(metadata)
    return _freeze_json(normalised)  # type: ignore[return-value]


def _normalise_truth(value: TruthValue | bool | str) -> TruthValue:
    if isinstance(value, TruthValue):
        return value
    if isinstance(value, bool):
        return TruthValue.TRUE if value else TruthValue.FALSE
    if isinstance(value, str):
        candidate = value.strip().lower()
        try:
            return TruthValue(candidate)
        except ValueError:
            try:
                return TruthValue[candidate.upper()]
            except KeyError as error:
                raise ValueError(
                    "value must be TRUE, FALSE, UNKNOWN, or CONFLICTING"
                ) from error
    raise TypeError(
        "value must be a bool, TruthValue, or one of the truth-value strings"
    )


def _normalise_source(source: EvidenceSource | str) -> EvidenceSource:
    if isinstance(source, EvidenceSource):
        return source
    if isinstance(source, str):
        candidate = source.strip().lower()
        try:
            return EvidenceSource(candidate)
        except ValueError:
            try:
                return EvidenceSource[candidate.upper()]
            except KeyError as error:
                raise ValueError(
                    "source must identify simulator, user, probe, prolog, "
                    "laya, policy, or system"
                ) from error
    raise TypeError("source must be an EvidenceSource or source name")


def _normalise_observation_time(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("observation time must be a valid ISO-8601 datetime") from error
    if not isinstance(value, datetime):
        raise TypeError("observation time must be a datetime, ISO-8601 string, or None")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalise_confidence(confidence: int | float) -> float:
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise TypeError("confidence must be a finite number between 0.0 and 1.0")
    confidence = float(confidence)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be a finite number between 0.0 and 1.0")
    return confidence


def _normalise_cycle(cycle: int | None) -> int | None:
    if cycle is None:
        return None
    if isinstance(cycle, bool) or not isinstance(cycle, int) or cycle < 0:
        raise ValueError("cycle must be a non-negative integer or None")
    return cycle


@dataclass(frozen=True, slots=True, init=False)
class Evidence:
    """One provenance-bearing observation about a predicate."""

    predicate: str
    value: TruthValue
    source: EvidenceSource
    observed_at: datetime | None
    metadata: Mapping[str, Any]
    confidence: float
    cycle: int | None

    def __init__(
        self,
        predicate: str,
        value: TruthValue | bool | str,
        source: EvidenceSource | str = EvidenceSource.SYSTEM,
        observed_at: datetime | str | None = None,
        metadata: Mapping[str, Any] | None = None,
        confidence: int | float = 1.0,
        cycle: int | None = None,
        *,
        observation_time: datetime | str | None = None,
    ) -> None:
        if not isinstance(predicate, str):
            raise TypeError("predicate must be a non-blank string")
        predicate = predicate.strip()
        if not predicate:
            raise ValueError("predicate must be a non-blank string")

        if observed_at is not None and observation_time is not None:
            first = _normalise_observation_time(observed_at)
            second = _normalise_observation_time(observation_time)
            if first != second:
                raise ValueError("observed_at and observation_time disagree")
        timestamp = _normalise_observation_time(
            observation_time if observation_time is not None else observed_at
        )

        object.__setattr__(self, "predicate", predicate)
        object.__setattr__(self, "value", _normalise_truth(value))
        object.__setattr__(self, "source", _normalise_source(source))
        object.__setattr__(self, "observed_at", timestamp)
        object.__setattr__(self, "metadata", _normalise_metadata(metadata))
        object.__setattr__(self, "confidence", _normalise_confidence(confidence))
        object.__setattr__(self, "cycle", _normalise_cycle(cycle))

    @property
    def observation_time(self) -> datetime | None:
        """Alias for :attr:`observed_at`."""

        return self.observed_at

    def canonical(self) -> dict[str, JSONValue]:
        return {
            "predicate": self.predicate,
            "value": self.value.value,
            "source": self.source.value,
            "observed_at": (
                self.observed_at.isoformat(timespec="microseconds")
                if self.observed_at is not None
                else None
            ),
            "metadata": _thaw_json(self.metadata),
            "confidence": self.confidence,
            "cycle": self.cycle,
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def to_dict(self) -> dict[str, JSONValue]:
        return self.canonical()

    def __hash__(self) -> int:
        return hash(self.canonical_json())

    @property
    def fingerprint(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()
