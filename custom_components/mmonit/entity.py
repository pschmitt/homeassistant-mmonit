"""Base entities for M/Monit."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlencode

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import CONF_MODE, DOMAIN, MODE_MMONIT
from .coordinator import MMonitDataUpdateCoordinator
from .models import MMonitCheck, MMonitHost


def get_host_device_identifier(entry_id: str, host_id: str) -> str:
    """Return the stable device identifier for one M/Monit host."""
    return f"{entry_id}:{host_id}"


def suggest_entity_id(
    domain: str,
    coordinator: MMonitDataUpdateCoordinator,
    host_id: str,
    suffix: str,
) -> str:
    """Suggest a mode-prefixed entity id (monit_* or mmonit_*).

    Only honored when the entity is first registered; existing registry
    entries keep their entity ids.
    """
    mode = coordinator.config_entry.data.get(CONF_MODE, MODE_MMONIT)
    host = coordinator.data.get(host_id)
    host_name = host.display_name if host else host_id
    return f"{domain}.{slugify(f'{mode} {host_name} {suffix}')}"


def iter_host_device_identifiers(
    entry_id: str,
    host_ids: Iterable[str],
) -> set[tuple[str, str]]:
    """Return the device identifiers for a collection of host IDs."""
    return {
        (DOMAIN, get_host_device_identifier(entry_id, host_id))
        for host_id in host_ids
    }


class MMonitHostEntity(CoordinatorEntity[MMonitDataUpdateCoordinator]):
    """Base M/Monit host entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MMonitDataUpdateCoordinator,
        host_id: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._host_id = host_id

    @property
    def host(self) -> MMonitHost | None:
        """Return the current host payload."""
        return self.coordinator.data.get(self._host_id)

    @property
    def available(self) -> bool:
        """Return whether the entity has current host data."""
        return self.coordinator.last_update_success and self.host is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information for the monitored host."""
        host = self.host
        if host is None:
            return None

        return DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    get_host_device_identifier(
                        self.coordinator.config_entry.entry_id,
                        host.host_id,
                    ),
                )
            },
            name=host.display_name,
            manufacturer=self.coordinator.client.manufacturer,
            model="Monitored Host",
            configuration_url=self.coordinator.server_url,
        )

    @property
    def host_url(self) -> str | None:
        """Return the server's detail URL for the current host."""
        host = self.host
        if host is None:
            return None

        return self.coordinator.client.get_host_url(host)


class MMonitEntity(MMonitHostEntity):
    """Base M/Monit check entity."""

    def __init__(
        self,
        coordinator: MMonitDataUpdateCoordinator,
        host_id: str,
        check_id: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, host_id)
        self._check_id = check_id

    @property
    def check(self) -> MMonitCheck | None:
        """Return the current check payload."""
        host = self.host
        if host is None:
            return None
        return host.checks.get(self._check_id)

    @property
    def available(self) -> bool:
        """Return whether the entity has current data."""
        return self.coordinator.last_update_success and self.check is not None

    @property
    def events_url(self) -> str | None:
        """Return the M/Monit events URL for the current check."""
        host = self.host
        check = self.check
        if host is None or check is None or check.name_id is None:
            return None

        host_name = host.hostname or host.name
        if not host_name:
            return None

        query = urlencode(
            {
                "reset": "true",
                "host": host_name,
                "servicenameid": check.name_id,
            }
        )
        return f"{self.coordinator.server_url}/reports/events/?{query}"
