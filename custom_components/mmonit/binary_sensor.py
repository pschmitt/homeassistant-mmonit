"""Binary sensor platform for M/Monit host status."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_FAILED_CHECKS,
    ATTR_HOST_COLOR,
    ATTR_HOST_SUMMARY,
    ATTR_LED,
    ATTR_SERVER_NAME,
    ATTR_SERVER_URL,
    DOMAIN,
)
from .coordinator import MMonitDataUpdateCoordinator
from .entity import MMonitHostEntity
from .registry import get_host_status_unique_id


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up M/Monit host status binary sensors from a config entry."""
    coordinator: MMonitDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        "coordinator"
    ]
    known_entities: set[str] = set()

    @callback
    def async_add_missing_entities() -> None:
        current_unique_ids: set[str] = set()
        new_entities: list[MMonitHostStatusBinarySensor] = []

        for host in coordinator.data.values():
            entity_unique_id = get_host_status_unique_id(
                config_entry.entry_id,
                host.host_id,
            )
            current_unique_ids.add(entity_unique_id)
            if entity_unique_id in known_entities:
                continue

            known_entities.add(entity_unique_id)
            new_entities.append(
                MMonitHostStatusBinarySensor(
                    coordinator=coordinator,
                    host_id=host.host_id,
                    unique_id=entity_unique_id,
                )
            )

        known_entities.clear()
        known_entities.update(current_unique_ids)

        if new_entities:
            async_add_entities(new_entities)

    async_add_missing_entities()
    config_entry.async_on_unload(
        coordinator.async_add_listener(async_add_missing_entities)
    )


class MMonitHostStatusBinarySensor(MMonitHostEntity, BinarySensorEntity):
    """Binary sensor summarizing the overall status of one host."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: MMonitDataUpdateCoordinator,
        host_id: str,
        unique_id: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, host_id)
        self._attr_unique_id = unique_id

    @property
    def name(self) -> str:
        """Return the entity name."""
        return "Status"

    @property
    def is_on(self) -> bool | None:
        """Return True when the host is in a problem state."""
        host = self.host
        if host is None or host.led is None:
            return None
        return host.led in {0, 1}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes for the host status."""
        host = self.host
        if host is None:
            return {}

        return {
            ATTR_FAILED_CHECKS: host.failed_checks,
            ATTR_HOST_COLOR: host.color,
            ATTR_HOST_SUMMARY: host.summary,
            ATTR_LED: host.led,
            ATTR_SERVER_NAME: self.coordinator.server_name,
            ATTR_SERVER_URL: self.coordinator.server_url,
        }
