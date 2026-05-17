"""Sensor platform for M/Monit checks."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_CHECK_ID,
    ATTR_CHECK_TYPE,
    ATTR_DATA_COLLECTED,
    ATTR_EVENTS_URL,
    ATTR_EVERY,
    ATTR_EVENTS,
    ATTR_LAST_EXIT_VALUE,
    ATTR_LAST_OUTPUT,
    ATTR_LED,
    ATTR_MONITOR_MODE,
    ATTR_MONITOR_STATE,
    ATTR_PORT_RESPONSE_TIME,
    ATTR_SERVER_NAME,
    ATTR_SERVER_URL,
    ATTR_STATUS_MESSAGE,
    DOMAIN,
)
from .coordinator import MMonitDataUpdateCoordinator
from .entity import MMonitEntity
from .registry import get_check_unique_id


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up M/Monit sensors from a config entry."""
    coordinator: MMonitDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id][
        "coordinator"
    ]
    known_entities: set[str] = set()

    @callback
    def async_add_missing_entities() -> None:
        current_unique_ids: set[str] = set()
        new_entities: list[MMonitCheckSensor] = []

        for host in coordinator.data.values():
            for check in host.checks.values():
                entity_unique_id = get_check_unique_id(
                    config_entry.entry_id,
                    host.host_id,
                    check.service_id,
                )
                current_unique_ids.add(entity_unique_id)
                if entity_unique_id in known_entities:
                    continue

                known_entities.add(entity_unique_id)
                new_entities.append(
                    MMonitCheckSensor(
                        coordinator=coordinator,
                        host_id=host.host_id,
                        check_id=check.service_id,
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


class MMonitCheckSensor(MMonitEntity, SensorEntity):
    """Sensor representing one M/Monit check."""

    def __init__(
        self,
        coordinator: MMonitDataUpdateCoordinator,
        host_id: str,
        check_id: str,
        unique_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, host_id, check_id)
        self._attr_unique_id = unique_id

    @property
    def name(self) -> str | None:
        """Return the entity name."""
        check = self.check
        if check is None:
            return None
        return check.name

    @property
    def native_value(self) -> str | None:
        """Return the M/Monit check state."""
        check = self.check
        if check is None:
            return None
        return check.status

    @property
    def icon(self) -> str:
        """Return an icon based on the M/Monit LED state."""
        check = self.check
        if check is None:
            return "mdi:help-circle-outline"

        return {
            0: "mdi:alert-circle",
            1: "mdi:alert",
            2: "mdi:check-circle",
            3: "mdi:pause-circle",
        }.get(check.led, "mdi:help-circle-outline")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes for the M/Monit check."""
        check = self.check
        if check is None:
            return {}

        attributes = {
            ATTR_STATUS_MESSAGE: check.message,
            ATTR_CHECK_ID: check.service_id,
            ATTR_CHECK_TYPE: check.check_type,
            ATTR_LED: check.led,
            ATTR_EVENTS: check.events,
            ATTR_EVERY: check.every,
            ATTR_MONITOR_MODE: check.monitor_mode,
            ATTR_MONITOR_STATE: check.monitor_state,
            ATTR_SERVER_NAME: self.coordinator.server_name,
            ATTR_SERVER_URL: self.coordinator.server_url,
        }

        if check.last_output is not None:
            attributes[ATTR_LAST_OUTPUT] = check.last_output
        if check.last_exit_value is not None:
            attributes[ATTR_LAST_EXIT_VALUE] = check.last_exit_value
        if check.port_response_time is not None:
            attributes[ATTR_PORT_RESPONSE_TIME] = check.port_response_time
        if check.data_collected is not None:
            attributes[ATTR_DATA_COLLECTED] = check.data_collected
        if self.events_url is not None:
            attributes[ATTR_EVENTS_URL] = self.events_url

        return attributes
