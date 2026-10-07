"""Async client for the Monarch REST API (bearer-token authentication)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote, urlparse

from aiohttp import ClientError, ClientResponseError, ClientSession

from .api import normalize_url
from .const import DEFAULT_REQUEST_TIMEOUT
from .exceptions import MMonitApiError, MMonitAuthenticationError
from .models import MMonitCheck, MMonitHost
from .monit_api import (
    LED_BLACK,
    LED_GREEN,
    LED_RED,
    LED_YELLOW,
    MONIT_SERVICE_TYPES,
    MonitApiClient,
)

_LOGGER = logging.getLogger(__name__)

# Monarch's coarse service state -> M/Monit LED.
_STATE_LED = {
    "ok": LED_GREEN,
    "failed": LED_RED,
    "unmonitored": LED_BLACK,
    "pending": LED_YELLOW,
    "init": LED_YELLOW,
}
_HOST_LED = {"ok": LED_GREEN, "degraded": LED_RED, "offline": LED_RED}

_STATE_TEXT = {
    "unmonitored": "Not monitored",
    "init": "Initializing",
    "pending": "Waiting",
}


class MonarchApiClient:
    """Thin async client for one Monarch server, authenticated with an API token."""

    manufacturer = "Monarch"

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        username: str,
        password: str,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        """Initialize the client.

        ``password`` carries the API token; ``username`` is unused and only kept
        so every client class shares one constructor signature.
        """
        del username
        self._session = session
        self._base_url = normalize_url(base_url)
        self._headers = {"Authorization": f"Bearer {password}", "Accept": "application/json"}
        self._request_timeout = request_timeout
        self._ids: dict[str, int] = {}

    @property
    def base_url(self) -> str:
        """Return the normalized base URL."""
        return self._base_url

    @property
    def server_name(self) -> str:
        """Return a friendly server name derived from the URL."""
        parsed = urlparse(self._base_url)
        return parsed.hostname or self._base_url

    def get_host_url(self, host: MMonitHost) -> str:
        """Return the web UI URL for the given host."""
        return f"{self._base_url}/hosts/{self._numeric_id(host.host_id)}"

    async def async_close(self) -> None:
        """Close the underlying session."""
        await self._session.close()

    async def async_validate_credentials(self) -> None:
        """Validate the configured token."""
        await self._request("GET", "/api/hosts")

    def _numeric_id(self, host_id: str) -> str:
        return str(self._ids.get(host_id, host_id))

    async def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self._base_url}{path}"
        try:
            async with asyncio.timeout(self._request_timeout):
                response = await self._session.request(
                    method, url, headers=self._headers, json=json
                )
                if response.status in {401, 403}:
                    raise MMonitAuthenticationError("Invalid or expired Monarch API token")
                if response.status >= 400:
                    detail = ""
                    try:
                        detail = (await response.json()).get("error", "")
                    except Exception:  # noqa: BLE001
                        pass
                    raise MMonitApiError(
                        f"HTTP {response.status} for {method} {path}"
                        + (f": {detail}" if detail else "")
                    )
                if response.status == 204:
                    return None
                return await response.json()
        except ClientResponseError as err:
            raise MMonitApiError(f"HTTP error {err.status} for {url}") from err
        except (ClientError, TimeoutError) as err:
            raise MMonitApiError(f"Request failed for {url}: {err!r}") from err

    async def async_fetch_hosts(self) -> dict[str, MMonitHost]:
        """Fetch every host with its services."""
        summaries = await self._request("GET", "/api/hosts")
        details = await asyncio.gather(
            *(self._request("GET", f"/api/hosts/{h['id']}") for h in summaries),
            return_exceptions=True,
        )
        hosts: dict[str, MMonitHost] = {}
        self._ids = {}
        for summary, detail in zip(summaries, details, strict=True):
            if isinstance(detail, MMonitAuthenticationError):
                raise detail
            if isinstance(detail, BaseException):
                # Left out of this poll; the coordinator keeps the last data for a while.
                _LOGGER.debug("Fetching Monarch host %s failed: %s", summary["id"], detail)
                continue
            host = self._normalize_host(detail)
            hosts[host.host_id] = host
            self._ids[host.host_id] = detail["id"]
        return hosts

    def _normalize_host(self, h: dict[str, Any]) -> MMonitHost:
        checks = {
            c.service_id: c for c in (self._normalize_check(s) for s in h.get("services", []))
        }
        failed = [c.name for c in checks.values() if c.led == LED_RED]
        if not checks:
            summary = "No checks"
        elif failed:
            summary = f"{len(failed)} of {len(checks)} checks failing"
        else:
            summary = f"All {len(checks)} checks OK"
        if not h.get("online", True):
            summary = "Offline"

        system = h.get("system") or {}
        load = system.get("load") or [None, None, None]
        os_info = h.get("os") or {}
        cpu_count = h.get("cpu_count")
        load_15 = load[2]
        load_per_core = (
            round(load_15 / cpu_count, 2) if load_15 is not None and cpu_count else None
        )
        swap = system.get("swap_percent")
        cpu = system.get("cpu")
        memory = system.get("mem_percent")

        checks = {
            cid: (
                _with_system_readings(
                    c, load, load_per_core, cpu, memory, swap
                )
                if c.type_id == 5
                else c
            )
            for cid, c in checks.items()
        }

        return MMonitHost(
            host_id=str(h["monit_id"]),
            name=str(h.get("display_name") or h.get("hostname") or h["monit_id"]),
            hostname=h.get("hostname"),
            summary=summary,
            led=_HOST_LED.get(h.get("state"), LED_BLACK),
            cpu=_round(cpu),
            memory=_round(memory),
            heartbeat=None,
            events=None,
            uptime=MonitApiClient._format_duration(_int(system.get("uptime"))),
            load_1=load[0],
            load_5=load[1],
            load_15=load[2],
            swap=_round(swap),
            cpu_count=cpu_count,
            memory_total_bytes=_kb(h.get("mem_total_kb")),
            swap_total_bytes=_kb(h.get("swap_total_kb")),
            platform_name=os_info.get("name"),
            platform_release=os_info.get("release"),
            platform_version=os_info.get("version"),
            platform_machine=os_info.get("machine"),
            monit_version=h.get("monit_version"),
            monit_uptime=MonitApiClient._format_duration(_int(h.get("monit_uptime"))),
            checks=checks,
        )

    def _normalize_check(self, s: dict[str, Any]) -> MMonitCheck:
        type_id = s.get("type_id")
        state = s.get("state", "init")
        data = s.get("data") or {}
        status_text = s.get("status_text") or ""
        failed = state == "failed"

        output = data.get("output") if type_id == 7 else None
        if isinstance(output, str):
            output = output.strip() or None

        pid = ppid = process_uptime = None
        if type_id == 3:
            pid = data.get("pid")
            ppid = data.get("ppid")
            process_uptime = MonitApiClient._format_duration(_int(data.get("uptime")))

        pending = s.get("pending_action")
        collected = s.get("collected_at")
        return MMonitCheck(
            service_id=s["name"],
            name=s["name"],
            check_type=MONIT_SERVICE_TYPES.get(type_id, s.get("type", "Unknown").title()),
            status="OK" if state == "ok" else _STATE_TEXT.get(state, status_text or "Failed"),
            message=status_text if failed else "",
            led=_STATE_LED.get(state, LED_YELLOW),
            events=s.get("events"),
            every=s.get("every"),
            monitor_mode=1 if s.get("monitor_mode") == "passive" else 0,
            monitor_state=s.get("monitor"),
            name_id=None,
            type_id=type_id,
            last_exit_value=data.get("exit_status") if type_id == 7 else None,
            last_output=output,
            port_response_time=None,
            data_collected=_iso(collected),
            check_group=(s.get("groups") or [None])[0],
            pending_action=pending or "none",
            pid=pid,
            ppid=ppid,
            process_uptime=process_uptime,
        )

    async def async_action(self, host_id: str, check_name: str, action: str) -> None:
        """Send start/stop/restart/monitor/unmonitor to a service via Monarch."""
        numeric = self._ids.get(host_id)
        if numeric is None:
            raise MMonitApiError(f"Unknown Monarch host {host_id!r}")
        await self._request(
            "POST",
            f"/api/hosts/{numeric}/services/{quote(check_name, safe='')}/action",
            {"action": action},
        )


def _with_system_readings(
    check: MMonitCheck,
    load: list[float | None],
    load_per_core: float | None,
    cpu: float | None,
    memory: float | None,
    swap: float | None,
) -> MMonitCheck:
    import dataclasses

    return dataclasses.replace(
        check,
        system_load_1=load[0],
        system_load_5=load[1],
        system_load_15=load[2],
        system_load_per_core=load_per_core,
        system_cpu_percent=_round(cpu),
        system_memory_percent=_round(memory),
        system_swap_percent=_round(swap),
        resource_summary=MonitApiClient._format_resource_summary(
            load_per_core, load[2], cpu, memory, swap
        ),
    )


def _int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any) -> float | None:
    try:
        return None if value is None else round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _kb(value: Any) -> int | None:
    n = _int(value)
    return None if n is None else n * 1024


def _iso(value: Any) -> str | None:
    from datetime import UTC, datetime

    try:
        return datetime.fromtimestamp(float(value), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None
