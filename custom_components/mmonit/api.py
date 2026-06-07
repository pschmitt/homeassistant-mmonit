"""Async M/Monit API client."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlencode, urlparse

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import (
    API_ACCEPT,
    DEFAULT_REQUEST_TIMEOUT,
    HOSTS_GET_PATH,
    HOSTS_LIST_PATH,
    LOGIN_PATH,
)
from .exceptions import MMonitApiError, MMonitAuthenticationError
from .models import MMonitCheck, MMonitHost

_LOGGER = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """Normalize a configured M/Monit URL."""
    return url.strip().rstrip("/")


class MMonitApiClient:
    """Thin async client for the M/Monit HTTP API."""

    manufacturer = "M/Monit"

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
        self._username = username
        self._password = password
        self._request_timeout = request_timeout
        self._login_lock = asyncio.Lock()

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
        """Return the M/Monit detail URL for the given host."""
        query = urlencode({"id": host.host_id})
        return f"{self._base_url}/status/hosts/detail?{query}"

    async def async_close(self) -> None:
        """Close the underlying session."""
        await self._session.close()

    async def async_validate_credentials(self) -> None:
        """Validate the configured credentials."""
        await self.async_fetch_hosts()

    async def async_fetch_hosts(self) -> dict[str, MMonitHost]:
        """Fetch all hosts and their checks from M/Monit."""
        payload = await self._async_request_json(HOSTS_LIST_PATH)
        records = self._extract_records(payload)

        if not isinstance(records, list):
            raise MMonitApiError("Unexpected response for hosts list")

        semaphore = asyncio.Semaphore(10)
        detail_tasks = [
            self._async_fetch_host_detail(semaphore, record)
            for record in records
            if isinstance(record, Mapping) and "id" in record
        ]
        detail_results = await asyncio.gather(*detail_tasks, return_exceptions=True)

        hosts: dict[str, MMonitHost] = {}
        for record, detail_result in zip(records, detail_results, strict=False):
            if not isinstance(record, Mapping):
                continue

            host_id = str(record.get("id", ""))
            if not host_id:
                continue

            if isinstance(detail_result, Exception):
                _LOGGER.warning("Skipping host %s after detail fetch failed: %s", host_id, detail_result)
                continue

            host = self._normalize_host(record, detail_result)
            hosts[host.host_id] = host

        if records and not hosts:
            raise MMonitApiError("Failed to fetch details for all discovered hosts")

        return hosts

    async def _async_fetch_host_detail(
        self,
        semaphore: asyncio.Semaphore,
        record: Mapping[str, Any],
    ) -> tuple[Any, str | None]:
        """Fetch the full detail payload for one host."""
        async with semaphore:
            payload, response_date = await self._async_request_json(
                HOSTS_GET_PATH,
                params={"id": str(record["id"])},
                include_response_date=True,
            )
            return payload, self._normalize_response_date(response_date)

    async def _async_request_json(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        retry_with_login: bool = True,
        include_response_date: bool = False,
    ) -> Any:
        """Perform a request and decode JSON, logging in when needed."""
        text, response_date = await self._async_request_text(
            endpoint,
            method=method,
            params=params,
            data=data,
        )
        payload = self._decode_json(text)

        if payload is None:
            if retry_with_login:
                await self._async_login()
                return await self._async_request_json(
                    endpoint,
                    method=method,
                    params=params,
                    data=data,
                    retry_with_login=False,
                    include_response_date=include_response_date,
                )
            raise MMonitAuthenticationError("Authentication failed")

        if include_response_date:
            return payload, response_date
        return payload

    async def _async_request_text(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> tuple[str, str | None]:
        """Perform a request and return the raw response body."""
        url = f"{self._base_url}/{endpoint.lstrip('/')}"

        try:
            async with asyncio.timeout(self._request_timeout):
                response = await self._session.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    allow_redirects=True,
                    headers={"Accept": API_ACCEPT},
                )
                response.raise_for_status()
                return await response.text(), response.headers.get("Date")
        except ClientResponseError as err:
            if err.status in {401, 403}:
                raise MMonitAuthenticationError("Invalid M/Monit credentials") from err
            raise MMonitApiError(f"HTTP error {err.status} for {endpoint}") from err
        except (ClientError, TimeoutError) as err:
            raise MMonitApiError(f"Request failed for {endpoint}") from err

    async def _async_login(self) -> None:
        """Authenticate with M/Monit and populate the session cookie jar."""
        async with self._login_lock:
            await self._async_request_text("index.csp")

            try:
                async with asyncio.timeout(self._request_timeout):
                    response = await self._session.post(
                        f"{self._base_url}/{LOGIN_PATH}",
                        data={
                            "z_username": self._username,
                            "z_password": self._password,
                            "z_csrf_protection": "off",
                        },
                        allow_redirects=True,
                        headers={"Accept": API_ACCEPT},
                    )
                    response.raise_for_status()
                    text = await response.text()
            except ClientResponseError as err:
                if err.status in {401, 403}:
                    raise MMonitAuthenticationError("Invalid M/Monit credentials") from err
                raise MMonitApiError("Login request failed") from err
            except (ClientError, TimeoutError) as err:
                raise MMonitApiError("Login request failed") from err

            login_payload = self._decode_json(text)
            if isinstance(login_payload, Mapping) and login_payload.get("error"):
                raise MMonitAuthenticationError(str(login_payload["error"]))

    @staticmethod
    def _decode_json(text: str) -> Any | None:
        """Decode JSON when the response body contains JSON."""
        stripped = text.strip()
        if not stripped or stripped[0] not in "{[":
            return None

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_records(payload: Any) -> Any:
        """Return the payload records block when present."""
        if isinstance(payload, Mapping) and "records" in payload:
            return payload["records"]
        return payload

    def _normalize_host(
        self,
        summary: Mapping[str, Any],
        detail_result: tuple[Any, str | None],
    ) -> MMonitHost:
        """Normalize one host from the summary and detail payloads."""
        detail_payload, data_collected = detail_result
        detail_records = self._extract_records(detail_payload)
        host_payload = detail_records.get("host") if isinstance(detail_records, Mapping) else detail_records
        if not isinstance(host_payload, Mapping):
            raise MMonitApiError("Unexpected host detail payload")

        checks: dict[str, MMonitCheck] = {}
        for service in host_payload.get("services", []):
            if not isinstance(service, Mapping):
                continue

            service_id = str(service.get("id") or service.get("nameid") or service.get("name") or "")
            if not service_id:
                continue

            checks[service_id] = MMonitCheck(
                service_id=service_id,
                name=str(service.get("name") or service_id),
                check_type=str(service.get("type") or "Unknown"),
                status=str(service.get("status") or "Unknown"),
                message=self._extract_status_message(service),
                led=self._as_int(service.get("led")),
                events=self._as_int(service.get("events")),
                every=self._as_str(service.get("every")),
                monitor_mode=self._as_int(service.get("monitormode")),
                monitor_state=self._as_int(service.get("monitorstate")),
                name_id=self._as_int(service.get("nameid")),
                type_id=self._as_int(service.get("typeid")),
                last_exit_value=self._extract_last_exit_value(service),
                last_output=self._extract_status_message(service) or None,
                port_response_time=self._extract_port_response_time(service),
                data_collected=data_collected,
            )

        return MMonitHost(
            host_id=str(summary.get("id") or host_payload.get("id") or ""),
            name=str(summary.get("hostname") or host_payload.get("name") or host_payload.get("hostname") or ""),
            hostname=self._as_str(host_payload.get("hostname")) or self._as_str(summary.get("hostname")),
            summary=str(summary.get("status") or ""),
            led=self._as_int(summary.get("led")),
            cpu=self._as_float(summary.get("cpu")),
            memory=self._as_float(summary.get("mem")),
            heartbeat=self._as_int(summary.get("heartbeat")),
            events=self._as_int(summary.get("events")),
            uptime=self._as_str(host_payload.get("uptime")) or self._as_str(host_payload.get("monit", {}).get("uptime")),
            cpu_count=self._as_int(host_payload.get("cpu", {}).get("count")),
            memory_total_bytes=self._kilobytes_to_bytes(host_payload.get("memory", {}).get("size")),
            swap_total_bytes=self._kilobytes_to_bytes(host_payload.get("swap", {}).get("size")),
            platform_name=self._as_str(host_payload.get("platform", {}).get("name")),
            platform_release=self._as_str(host_payload.get("platform", {}).get("release")),
            platform_version=self._as_str(host_payload.get("platform", {}).get("version")),
            platform_machine=self._as_str(host_payload.get("platform", {}).get("machine")),
            monit_version=self._as_str(host_payload.get("monit", {}).get("version")),
            monit_uptime=self._as_str(host_payload.get("monit", {}).get("uptime")),
            checks=checks,
        )

    @staticmethod
    def _extract_status_message(service: Mapping[str, Any]) -> str:
        """Extract the detailed status message from a service payload."""
        statistics = service.get("statistics")
        if not isinstance(statistics, list):
            return ""

        for item in statistics:
            if not isinstance(item, Mapping):
                continue
            if item.get("type") == 35:
                return str(item.get("value") or "").strip()
        return ""

    def _extract_last_exit_value(self, service: Mapping[str, Any]) -> int | None:
        """Extract the last exit value from a service payload."""
        statistic = self._get_statistic(service, 24)
        if statistic is None:
            return None
        return self._as_int(statistic.get("value"))

    def _extract_port_response_time(self, service: Mapping[str, Any]) -> str | None:
        """Extract and format the port response time from a service payload."""
        statistic = self._get_statistic(service, 15)
        if statistic is None:
            return None

        response_time_seconds = self._as_float(statistic.get("value"))
        if response_time_seconds is None:
            return None

        descriptor = self._as_str(statistic.get("descriptor")) or ""
        target, protocol, transport = self._parse_port_descriptor(descriptor)
        tls_days = self._extract_tls_certificate_days(service)

        parts = [f"{response_time_seconds * 1000:.3f} ms"]
        if target:
            parts.append(f"to {target}")

        transport_label = transport
        if transport == "TCP":
            transport_label = "TCP/IP"
        elif transport == "UDP":
            transport_label = "UDP/IP"

        if transport_label:
            if tls_days is not None:
                parts.append(
                    f"type {transport_label} using TLS (certificate valid for {tls_days} days)"
                )
            else:
                parts.append(f"type {transport_label}")

        if protocol:
            parts.append(f"protocol {protocol}")

        return " ".join(parts)

    def _extract_tls_certificate_days(self, service: Mapping[str, Any]) -> int | None:
        """Extract the TLS certificate validity window in days."""
        statistic = self._get_statistic(service, 75)
        if statistic is None:
            return None
        return self._as_int(statistic.get("value"))

    @staticmethod
    def _get_statistic(
        service: Mapping[str, Any],
        statistic_type: int,
    ) -> Mapping[str, Any] | None:
        """Return one statistic by type."""
        statistics = service.get("statistics")
        if not isinstance(statistics, list):
            return None

        for item in statistics:
            if not isinstance(item, Mapping):
                continue
            if item.get("type") == statistic_type:
                return item
        return None

    @staticmethod
    def _parse_port_descriptor(
        descriptor: str,
    ) -> tuple[str | None, str | None, str | None]:
        """Parse a port response descriptor into target, protocol, and transport."""
        if not descriptor:
            return None, None, None

        if " [" not in descriptor or not descriptor.endswith("]"):
            return descriptor, None, None

        target, suffix = descriptor.rsplit(" [", 1)
        details = suffix[:-1]
        if "/" not in details:
            return target, details or None, None

        protocol, transport = details.split("/", 1)
        return target, protocol or None, transport or None

    @staticmethod
    def _normalize_response_date(value: str | None) -> str | None:
        """Normalize an HTTP response date to an ISO timestamp."""
        if not value:
            return None
        try:
            return parsedate_to_datetime(value).isoformat()
        except (TypeError, ValueError, IndexError):
            return value

    @staticmethod
    def _as_int(value: Any) -> int | None:
        """Convert a value to int when possible."""
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_float(value: Any) -> float | None:
        """Convert a value to float when possible."""
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_str(value: Any) -> str | None:
        """Convert a value to string when present."""
        if value in (None, ""):
            return None
        return str(value)

    def _kilobytes_to_bytes(self, value: Any) -> int | None:
        """Convert a kibibyte value to bytes when possible."""
        kibibytes = self._as_int(value)
        if kibibytes is None:
            return None
        return kibibytes * 1024
