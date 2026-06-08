"""Async client for the embedded Monit httpd status API."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from urllib.parse import quote, urlparse

from aiohttp import BasicAuth, ClientError, ClientResponseError, ClientSession

from .api import normalize_url
from .const import DEFAULT_REQUEST_TIMEOUT, MONIT_EVENTS_PATH, MONIT_STATUS_PATH
from .exceptions import MMonitApiError, MMonitAuthenticationError
from .models import MMonitCheck, MMonitHost

_LOGGER = logging.getLogger(__name__)

# Monit declares ISO-8859-1 in the XML prolog but emits raw UTF-8 bytes for
# e.g. program output. Strip the prolog and decode as UTF-8 ourselves.
_XML_DECLARATION_RE = re.compile(r"^\s*<\?xml[^>]*\?>")

# LED semantics shared with M/Monit: 0=red, 1=yellow, 2=green, 3=black.
LED_RED = 0
LED_YELLOW = 1
LED_GREEN = 2
LED_BLACK = 3

# Monit <monitor> state is a bitmask: 1=active, 2=initializing, 4=waiting.
MONITOR_ACTIVE = 0x1
MONITOR_INIT = 0x2
MONITOR_WAITING = 0x4

MONIT_SERVICE_TYPES: dict[int, str] = {
    0: "Filesystem",
    1: "Directory",
    2: "File",
    3: "Process",
    4: "Remote Host",
    5: "System",
    6: "Fifo",
    7: "Program",
    8: "Network",
}

# Monit <status> is a bitmask of failed events (Event_* in monit's event.h).
MONIT_EVENT_DESCRIPTIONS: dict[int, str] = {
    0x1: "Checksum failed",
    0x2: "Resource limit matched",
    0x4: "Timeout",
    0x8: "Timestamp failed",
    0x10: "Size failed",
    0x20: "Connection failed",
    0x40: "Permission failed",
    0x80: "UID failed",
    0x100: "GID failed",
    0x200: "Does not exist",
    0x400: "Invalid type",
    0x800: "Data access error",
    0x1000: "Execution failed",
    0x2000: "Filesystem flags failed",
    0x4000: "ICMP failed",
    0x8000: "Content failed",
    0x10000: "Monit instance changed",
    0x20000: "Action done",
    0x40000: "PID failed",
    0x80000: "PPID failed",
    0x100000: "Heartbeat failed",
    0x200000: "Status failed",
    0x400000: "Uptime failed",
    0x800000: "Link down",
    0x1000000: "Speed failed",
    0x2000000: "Saturation exceeded",
    0x4000000: "Download bytes exceeded",
    0x8000000: "Upload bytes exceeded",
    0x10000000: "Download packets exceeded",
    0x20000000: "Upload packets exceeded",
    0x40000000: "Exists",
}


class MonitApiClient:
    """Thin async client for one Monit instance's embedded httpd."""

    manufacturer = "Monit"

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        username: str,
        password: str,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._base_url = normalize_url(base_url)
        self._auth = BasicAuth(username, password)
        self._request_timeout = request_timeout

    @property
    def base_url(self) -> str:
        """Return the normalized base URL."""
        return self._base_url

    @property
    def server_name(self) -> str:
        """Return a friendly server name derived from the URL."""
        parsed = urlparse(self._base_url)
        if parsed.hostname:
            return parsed.hostname
        return self._base_url

    def get_host_url(self, host: MMonitHost) -> str:
        """Return the web UI URL for the given host."""
        del host
        return self._base_url

    async def async_close(self) -> None:
        """Close the underlying session."""
        await self._session.close()

    async def async_validate_credentials(self) -> None:
        """Validate the configured credentials."""
        await self.async_fetch_hosts()

    async def async_fetch_hosts(self) -> dict[str, MMonitHost]:
        """Fetch the status of this Monit instance as a single-host mapping."""
        url = f"{self._base_url}/{MONIT_STATUS_PATH}"

        try:
            async with asyncio.timeout(self._request_timeout):
                response = await self._session.get(
                    url,
                    params={"format": "xml"},
                    auth=self._auth,
                    allow_redirects=True,
                )
                response.raise_for_status()
                raw = await response.read()
        except ClientResponseError as err:
            if err.status in {401, 403}:
                raise MMonitAuthenticationError("Invalid Monit credentials") from err
            raise MMonitApiError(f"HTTP error {err.status} for {url}") from err
        except (ClientError, TimeoutError) as err:
            raise MMonitApiError(f"Request failed for {url}") from err

        host = self._parse_status(raw)
        events_by_service = await self._async_fetch_events()
        if events_by_service:
            updated_checks = {
                cid: dataclasses.replace(chk, last_events=events_by_service.get(chk.name, []))
                for cid, chk in host.checks.items()
            }
            host = dataclasses.replace(host, checks=updated_checks)
        return {host.host_id: host}

    async def _async_fetch_events(self) -> dict[str, list[dict]]:
        """Fetch per-check event history from /_events?format=xml."""
        url = f"{self._base_url}/{MONIT_EVENTS_PATH}"
        try:
            async with asyncio.timeout(self._request_timeout):
                response = await self._session.get(
                    url,
                    params={"format": "xml"},
                    auth=self._auth,
                    allow_redirects=True,
                )
                response.raise_for_status()
                raw = await response.read()
        except (ClientResponseError, ClientError, TimeoutError) as err:
            _LOGGER.debug("Could not fetch monit events from %s: %s", url, err)
            return {}
        return self._parse_events(raw)

    def _parse_events(self, raw: bytes) -> dict[str, list[dict]]:
        """Parse monit events XML into {service_name: [events]} most-recent first."""
        text = _XML_DECLARATION_RE.sub("", raw.decode("utf-8", errors="replace"))
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return {}
        if root.tag != "monit":
            return {}

        by_service: dict[str, list[dict]] = {}
        for event in root.iter("event"):
            name = self._as_str(event.findtext("service"))
            if not name:
                continue
            ts_sec = self._as_int(event.findtext("collected_sec")) or 0
            message = (self._as_str(event.findtext("message")) or "").strip()
            state = self._as_int(event.findtext("state")) or 0
            by_service.setdefault(name, []).append(
                {"time": self._timestamp_to_iso(str(ts_sec)), "message": message, "state": state, "_ts": ts_sec}
            )

        result: dict[str, list[dict]] = {}
        for name, evts in by_service.items():
            evts.sort(key=lambda e: e["_ts"], reverse=True)
            result[name] = [{"time": e["time"], "message": e["message"], "state": e["state"]} for e in evts[:20]]
        return result

    def _parse_status(self, raw: bytes) -> MMonitHost:
        """Parse a Monit status XML document into one normalized host."""
        text = _XML_DECLARATION_RE.sub("", raw.decode("utf-8", errors="replace"))
        try:
            root = ET.fromstring(text)
        except ET.ParseError as err:
            raise MMonitApiError("Failed to parse Monit status XML") from err

        if root.tag != "monit":
            raise MMonitApiError("Unexpected Monit status payload")

        hostname = root.findtext("server/localhostname")
        host_id = root.findtext("server/id") or self.server_name

        checks: dict[str, MMonitCheck] = {}
        system_service: ET.Element | None = None
        for service in root.iter("service"):
            check = self._normalize_check(service)
            if check is None:
                continue
            checks[check.service_id] = check
            if self._as_int(service.get("type")) == 5:
                system_service = service

        led = self._derive_host_led(checks)
        failed = [check.name for check in checks.values() if check.led == LED_RED]
        if not checks:
            summary = "No checks"
        elif failed:
            summary = f"{len(failed)} of {len(checks)} checks failing"
        else:
            summary = f"All {len(checks)} checks OK"

        cpu = memory = None
        uptime = None
        if system_service is not None:
            cpu_user = self._as_float(system_service.findtext("system/cpu/user"))
            cpu_system = self._as_float(system_service.findtext("system/cpu/system"))
            cpu_wait = self._as_float(system_service.findtext("system/cpu/wait"))
            cpu_parts = [part for part in (cpu_user, cpu_system, cpu_wait) if part is not None]
            if cpu_parts:
                cpu = round(sum(cpu_parts), 1)
            memory = self._as_float(system_service.findtext("system/memory/percent"))
            uptime = self._format_duration(self._as_int(system_service.findtext("uptime")))

        return MMonitHost(
            host_id=str(host_id),
            name=str(hostname or self.server_name),
            hostname=self._as_str(hostname),
            summary=summary,
            led=led,
            cpu=cpu,
            memory=memory,
            heartbeat=None,
            events=None,
            uptime=uptime,
            cpu_count=self._as_int(root.findtext("platform/cpu")),
            memory_total_bytes=self._kilobytes_to_bytes(root.findtext("platform/memory")),
            swap_total_bytes=self._kilobytes_to_bytes(root.findtext("platform/swap")),
            platform_name=self._as_str(root.findtext("platform/name")),
            platform_release=self._as_str(root.findtext("platform/release")),
            platform_version=self._as_str(root.findtext("platform/version")),
            platform_machine=self._as_str(root.findtext("platform/machine")),
            monit_version=self._as_str(root.findtext("server/version")),
            monit_uptime=self._format_duration(self._as_int(root.findtext("server/uptime"))),
            checks=checks,
        )

    def _normalize_check(self, service: ET.Element) -> MMonitCheck | None:
        """Normalize one Monit service element."""
        name = service.findtext("name")
        if not name:
            return None

        type_id = self._as_int(service.get("type"))
        status = self._as_int(service.findtext("status")) or 0
        monitor = self._as_int(service.findtext("monitor")) or 0
        led = self._derive_check_led(status, monitor)

        message = self._describe_status(status)
        last_output = self._as_str(service.findtext("program/output"))
        if last_output is not None:
            last_output = last_output.strip() or None

        check_group = self._as_str(service.findtext("group"))
        on_reboot_val = self._as_int(service.findtext("onreboot"))
        on_reboot = {0: "start", 1: "stop", 2: "noaction"}.get(on_reboot_val) if on_reboot_val is not None else None
        pending_action_val = self._as_int(service.findtext("pendingaction"))
        pending_action = {
            0: "none", 1: "stop", 2: "start", 3: "restart", 4: "alert", 5: "exec",
        }.get(pending_action_val) if pending_action_val is not None else None
        action_start = self._as_str(service.findtext("start/path"))
        action_stop = self._as_str(service.findtext("stop/path"))
        action_restart = self._as_str(service.findtext("restart/path"))

        check_path = None
        if type_id == 7:  # Program
            check_path = self._as_str(service.findtext("program/path"))

        pid = ppid = process_uptime = None
        if type_id == 3:  # Process
            pid = self._as_int(service.findtext("pid"))
            ppid = self._as_int(service.findtext("ppid"))
            process_uptime = self._format_duration(self._as_int(service.findtext("uptime")))

        return MMonitCheck(
            service_id=name,
            name=name,
            check_type=MONIT_SERVICE_TYPES.get(type_id, "Unknown"),
            status=self._status_text(status, monitor),
            message=message,
            led=led,
            events=None,
            every=self._extract_every(service),
            monitor_mode=self._as_int(service.findtext("monitormode")),
            monitor_state=monitor,
            name_id=None,
            type_id=type_id,
            last_exit_value=self._as_int(service.findtext("program/status")),
            last_output=last_output,
            port_response_time=self._extract_response_time(service),
            data_collected=self._timestamp_to_iso(service.findtext("collected_sec")),
            check_path=check_path,
            check_group=check_group,
            action_start=action_start,
            action_stop=action_stop,
            action_restart=action_restart,
            on_reboot=on_reboot,
            pending_action=pending_action,
            pid=pid,
            ppid=ppid,
            process_uptime=process_uptime,
        )

    @staticmethod
    def _derive_check_led(status: int, monitor: int) -> int:
        """Derive an M/Monit-style LED state for one check."""
        if monitor == 0:
            return LED_BLACK
        if monitor & MONITOR_INIT:
            # Genuinely initializing — last status unknown.
            return LED_YELLOW
        if monitor & MONITOR_WAITING:
            # Between cycles: status still reflects the last completed check.
            return LED_RED if status != 0 else LED_GREEN
        if status != 0:
            return LED_RED
        return LED_GREEN

    @staticmethod
    def _derive_host_led(checks: dict[str, MMonitCheck]) -> int:
        """Derive an M/Monit-style LED state for the whole host.

        Initializing checks (yellow) are not treated as a host problem: checks
        on a cron-style schedule spend most of their time in that state.
        """
        leds = {check.led for check in checks.values()}
        if LED_RED in leds:
            return LED_RED
        if leds and leds <= {LED_BLACK}:
            return LED_BLACK
        return LED_GREEN

    @staticmethod
    def _status_text(status: int, monitor: int) -> str:
        """Return a compact state string for one check."""
        if monitor == 0:
            return "Not monitored"
        if monitor & MONITOR_INIT:
            return "Initializing"
        if monitor & MONITOR_WAITING:
            return "Waiting"
        if status == 0:
            return "OK"
        return MonitApiClient._describe_status(status) or "Failed"

    @staticmethod
    def _describe_status(status: int) -> str:
        """Describe the failed events encoded in a status bitmask."""
        if status == 0:
            return ""
        descriptions = [
            description
            for bit, description in MONIT_EVENT_DESCRIPTIONS.items()
            if status & bit
        ]
        if not descriptions:
            return f"Failed (status {status})"
        return ", ".join(descriptions)

    def _extract_every(self, service: ET.Element) -> str | None:
        """Extract the check cadence when one is configured."""
        cron = self._as_str(service.findtext("every/cron"))
        if cron is not None:
            return cron
        number = self._as_int(service.findtext("every/number"))
        if number:
            return f"{number} cycles"
        return None

    def _extract_response_time(self, service: ET.Element) -> str | None:
        """Extract and format the port or ICMP response time."""
        port = service.find("port")
        if port is not None:
            response_time = self._as_float(port.findtext("responsetime"))
            if response_time is None:
                return None
            parts = [f"{response_time * 1000:.3f} ms"]
            hostname = self._as_str(port.findtext("hostname"))
            port_number = self._as_str(port.findtext("portnumber"))
            if hostname and port_number:
                parts.append(f"to {hostname}:{port_number}")
            transport = self._as_str(port.findtext("type"))
            if transport:
                transport_label = {"TCP": "TCP/IP", "UDP": "UDP/IP"}.get(transport, transport)
                certificate_days = self._as_int(port.findtext("certificate/valid"))
                if certificate_days is not None:
                    parts.append(
                        f"type {transport_label} using TLS "
                        f"(certificate valid for {certificate_days} days)"
                    )
                else:
                    parts.append(f"type {transport_label}")
            protocol = self._as_str(port.findtext("protocol"))
            if protocol:
                parts.append(f"protocol {protocol}")
            return " ".join(parts)

        icmp = service.find("icmp")
        if icmp is not None:
            response_time = self._as_float(icmp.findtext("responsetime"))
            if response_time is None:
                return None
            icmp_type = self._as_str(icmp.findtext("type")) or "Ping"
            return f"{response_time * 1000:.3f} ms (ICMP {icmp_type})"

        return None

    @staticmethod
    def _format_duration(seconds: int | None) -> str | None:
        """Format a duration in seconds as an M/Monit-style string."""
        if seconds is None:
            return None
        minutes, _ = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        if days:
            return f"{days}d {hours}h {minutes}m"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _timestamp_to_iso(self, value: str | None) -> str | None:
        """Convert an epoch timestamp to an ISO timestamp."""
        timestamp = self._as_int(value)
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()

    @staticmethod
    def _as_int(value: str | None) -> int | None:
        """Convert a value to int when possible."""
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_float(value: str | None) -> float | None:
        """Convert a value to float when possible."""
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_str(value: str | None) -> str | None:
        """Convert a value to string when present."""
        if value in (None, ""):
            return None
        return str(value)

    async def async_action(self, host_id: str, check_name: str, action: str) -> None:
        """Send start/stop/restart/monitor/unmonitor to a Monit service."""
        url = f"{self._base_url}/{quote(check_name, safe='')}"
        try:
            async with asyncio.timeout(self._request_timeout):
                get_resp = await self._session.get(
                    url,
                    auth=self._auth,
                    allow_redirects=True,
                )
                get_resp.raise_for_status()

                security_token = get_resp.cookies.get("securitytoken")
                if security_token is None:
                    raise MMonitApiError(
                        f"No securitytoken cookie from Monit for {check_name!r}"
                    )

                response = await self._session.post(
                    url,
                    data={"securitytoken": security_token.value, "action": action},
                    auth=self._auth,
                    allow_redirects=False,
                )
                if response.status >= 400:
                    response.raise_for_status()
        except ClientResponseError as err:
            if err.status in {401, 403}:
                raise MMonitAuthenticationError(
                    f"Authentication failed sending {action!r} to {check_name!r}"
                ) from err
            raise MMonitApiError(
                f"HTTP {err.status} sending {action!r} to {check_name!r}"
            ) from err
        except (ClientError, TimeoutError) as err:
            raise MMonitApiError(
                f"Request failed sending {action!r} to {check_name!r}"
            ) from err

    def _kilobytes_to_bytes(self, value: str | None) -> int | None:
        """Convert a kibibyte value to bytes when possible."""
        kibibytes = self._as_int(value)
        if kibibytes is None:
            return None
        return kibibytes * 1024
