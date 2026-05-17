"""Normalized data models for M/Monit."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class MMonitCheck:
    """One normalized M/Monit check."""

    service_id: str
    name: str
    check_type: str
    status: str
    message: str
    led: int | None
    events: int | None
    every: str | None
    monitor_mode: int | None
    monitor_state: int | None
    name_id: int | None
    type_id: int | None


@dataclass(slots=True, frozen=True)
class MMonitHost:
    """One normalized M/Monit host."""

    host_id: str
    name: str
    hostname: str | None
    summary: str
    led: int | None
    cpu: float | None
    memory: float | None
    heartbeat: int | None
    events: int | None
    checks: dict[str, MMonitCheck]

    @property
    def display_name(self) -> str:
        """Return the best host display name."""
        return self.name or self.hostname or self.host_id

    @property
    def color(self) -> str:
        """Return the M/Monit color name for this host."""
        return {
            0: "red",
            1: "yellow",
            2: "green",
            3: "black",
        }.get(self.led, "unknown")
