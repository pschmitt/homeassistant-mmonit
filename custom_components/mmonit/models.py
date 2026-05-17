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
    last_exit_value: int | None
    last_output: str | None
    port_response_time: str | None
    data_collected: str | None


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
    uptime: str | None
    cpu_count: int | None
    memory_total_bytes: int | None
    swap_total_bytes: int | None
    platform_name: str | None
    platform_release: str | None
    platform_version: str | None
    platform_machine: str | None
    monit_version: str | None
    monit_uptime: str | None
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

    @property
    def failed_checks(self) -> list[str]:
        """Return the names of failed checks for this host."""
        return [
            check.name
            for check in self.checks.values()
            if check.led in {0, 1}
        ]

    @property
    def platform_display(self) -> str | None:
        """Return a compact platform label."""
        if not self.platform_name and not self.platform_release:
            return None
        if self.platform_name and self.platform_release:
            return f"{self.platform_name} {self.platform_release}"
        return self.platform_name or self.platform_release
