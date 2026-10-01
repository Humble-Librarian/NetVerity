"""Deterministic network environment test simulator."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .evidence import Evidence, EvidenceSource


@dataclass(frozen=True, slots=True)
class NetworkEnvironment:
    """Network environment properties for simulation."""

    wifi_connected: bool = True
    has_valid_ip: bool = True
    gateway_reachable: bool = True
    internet_ip_reachable: bool = True
    dns_resolution_ok: bool = True
    packet_loss_high: bool = False
    firewall_blocking_traffic: bool = False
    ip_conflict_detected: bool = False
    proxy_enabled: bool = False
    proxy_reachable: bool = True
    ethernet_connected: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NetworkEnvironment:
        known_keys = {
            "wifi_connected",
            "has_valid_ip",
            "gateway_reachable",
            "internet_ip_reachable",
            "dns_resolution_ok",
            "packet_loss_high",
            "firewall_blocking_traffic",
            "ip_conflict_detected",
            "proxy_enabled",
            "proxy_reachable",
            "ethernet_connected",
        }
        kwargs: dict[str, Any] = {k: bool(v) for k, v in data.items() if k in known_keys}
        extra_meta = {k: v for k, v in data.items() if k not in known_keys and k != "ground_truth"}
        return cls(**kwargs, metadata=extra_meta)


@dataclass(frozen=True, slots=True)
class Scenario:
    """A diagnostic test scenario with environmental conditions and evaluation metadata."""

    scenario_id: str
    name: str
    description: str
    initial_user_symptoms: str
    environment: NetworkEnvironment
    ground_truth_fault: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def load_json(cls, path: str | Path) -> Scenario:
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        env = NetworkEnvironment.from_dict(data.get("environment", {}))
        return cls(
            scenario_id=data.get("scenario_id", path.stem),
            name=data.get("name", path.stem.replace("_", " ").title()),
            description=data.get("description", ""),
            initial_user_symptoms=data.get("initial_user_symptoms", ""),
            environment=env,
            ground_truth_fault=data.get("ground_truth_fault", ""),
            metadata=data.get("metadata", {}),
        )


class DiagnosticTestSimulator:
    """Executes network diagnostic tests against a simulated network environment.

    CRITICAL PRINCIPLE: Tests return ONLY environmental observations (Evidence),
    NEVER the diagnosis.
    """

    def __init__(self, environment: NetworkEnvironment | None = None) -> None:
        self.environment = environment or NetworkEnvironment()

    def check_wifi(self, cycle: int = 1) -> Evidence:
        return Evidence(
            predicate="wifi_connected",
            value=self.environment.wifi_connected,
            source=EvidenceSource.SIMULATOR,
            cycle=cycle,
            metadata={"test": "check_wifi", "latency_ms": 12},
        )

    def check_ip(self, cycle: int = 1) -> Evidence:
        return Evidence(
            predicate="has_valid_ip",
            value=self.environment.has_valid_ip,
            source=EvidenceSource.SIMULATOR,
            cycle=cycle,
            metadata={"test": "check_ip", "latency_ms": 15},
        )

    def check_gateway(self, cycle: int = 1) -> Evidence:
        return Evidence(
            predicate="gateway_reachable",
            value=self.environment.gateway_reachable,
            source=EvidenceSource.SIMULATOR,
            cycle=cycle,
            metadata={"test": "check_gateway", "latency_ms": 25},
        )

    def ping_public_ip(self, cycle: int = 1) -> Evidence:
        return Evidence(
            predicate="internet_ip_reachable",
            value=self.environment.internet_ip_reachable,
            source=EvidenceSource.SIMULATOR,
            cycle=cycle,
            metadata={"test": "ping_public_ip", "target": "8.8.8.8", "latency_ms": 35},
        )

    def check_dns(self, cycle: int = 1) -> Evidence:
        return Evidence(
            predicate="dns_resolution_ok",
            value=self.environment.dns_resolution_ok,
            source=EvidenceSource.SIMULATOR,
            cycle=cycle,
            metadata={"test": "check_dns", "target": "example.com", "latency_ms": 40},
        )

    def check_packet_loss(self, cycle: int = 1) -> Evidence:
        return Evidence(
            predicate="packet_loss_high",
            value=self.environment.packet_loss_high,
            source=EvidenceSource.SIMULATOR,
            cycle=cycle,
            metadata={"test": "check_packet_loss", "samples": 50, "latency_ms": 150},
        )

    def check_firewall(self, cycle: int = 1) -> Evidence:
        return Evidence(
            predicate="firewall_blocking_traffic",
            value=self.environment.firewall_blocking_traffic,
            source=EvidenceSource.SIMULATOR,
            cycle=cycle,
            metadata={"test": "check_firewall", "latency_ms": 30},
        )

    def check_ip_conflict(self, cycle: int = 1) -> Evidence:
        return Evidence(
            predicate="ip_conflict_detected",
            value=self.environment.ip_conflict_detected,
            source=EvidenceSource.SIMULATOR,
            cycle=cycle,
            metadata={"test": "check_ip_conflict", "latency_ms": 45},
        )

    def check_proxy(self, cycle: int = 1) -> Evidence:
        return Evidence(
            predicate="proxy_reachable",
            value=self.environment.proxy_reachable,
            source=EvidenceSource.SIMULATOR,
            cycle=cycle,
            metadata={"test": "check_proxy", "latency_ms": 20},
        )

    def check_ethernet(self, cycle: int = 1) -> Evidence:
        return Evidence(
            predicate="ethernet_connected",
            value=self.environment.ethernet_connected,
            source=EvidenceSource.SIMULATOR,
            cycle=cycle,
            metadata={"test": "check_ethernet", "latency_ms": 10},
        )

    def run_test(self, action_name: str, cycle: int = 1) -> list[Evidence]:
        """Dispatch test by action name and return observed evidence."""
        dispatch_table = {
            "check_wifi": self.check_wifi,
            "check_ip": self.check_ip,
            "check_gateway": self.check_gateway,
            "ping_public_ip": self.ping_public_ip,
            "check_dns": self.check_dns,
            "check_packet_loss": self.check_packet_loss,
            "check_firewall": self.check_firewall,
            "check_ip_conflict": self.check_ip_conflict,
            "check_proxy": self.check_proxy,
            "check_ethernet": self.check_ethernet,
        }
        test_fn = dispatch_table.get(action_name)
        if not test_fn:
            raise ValueError(f"Unknown diagnostic action: {action_name}")
        return [test_fn(cycle=cycle)]
