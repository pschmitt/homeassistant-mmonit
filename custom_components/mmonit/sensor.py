"""Sensor platform for M/Monit checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfInformation
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_CHECK_ID,
    ATTR_CHECK_TYPE,
    ATTR_DATA_COLLECTED,
    ATTR_EVENTS_URL,
    ATTR_EVERY,
    ATTR_EVENTS,
    ATTR_LAST_EVENTS,
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
    HOST_SENSOR_CPU_COUNT,
    HOST_SENSOR_CPU_USAGE,
    HOST_SENSOR_MEMORY_TOTAL,
    HOST_SENSOR_MEMORY_USAGE,
    HOST_SENSOR_PLATFORM,
    HOST_SENSOR_SWAP_TOTAL,
    HOST_SENSOR_UPTIME,
)
from .coordinator import MMonitDataUpdateCoordinator
from .entity import MMonitEntity, MMonitHostEntity, suggest_entity_id
from .registry import get_check_unique_id, get_host_metric_unique_id


@dataclass(frozen=True, kw_only=True)
class MMonitHostSensorDescription(SensorEntityDescription):
    """Description of a host-level M/Monit sensor."""

    value_attr: str


HOST_SENSOR_DESCRIPTIONS: tuple[MMonitHostSensorDescription, ...] = (
    MMonitHostSensorDescription(
        key=HOST_SENSOR_CPU_USAGE,
        name="CPU Usage",
        icon="mdi:cpu-64-bit",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_attr="cpu",
    ),
    MMonitHostSensorDescription(
        key=HOST_SENSOR_MEMORY_USAGE,
        name="Memory Usage",
        icon="mdi:memory",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_attr="memory",
    ),
    MMonitHostSensorDescription(
        key=HOST_SENSOR_UPTIME,
        name="Uptime",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_attr="uptime",
    ),
    MMonitHostSensorDescription(
        key=HOST_SENSOR_CPU_COUNT,
        name="CPU Count",
        icon="mdi:chip",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_attr="cpu_count",
    ),
    MMonitHostSensorDescription(
        key=HOST_SENSOR_MEMORY_TOTAL,
        name="Memory Total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_attr="memory_total_bytes",
    ),
    MMonitHostSensorDescription(
        key=HOST_SENSOR_SWAP_TOTAL,
        name="Swap Total",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_attr="swap_total_bytes",
    ),
    MMonitHostSensorDescription(
        key=HOST_SENSOR_PLATFORM,
        name="Platform",
        icon="mdi:desktop-classic",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_attr="platform_display",
    ),
)


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
        new_entities: list[SensorEntity] = []

        for host in coordinator.data.values():
            for description in HOST_SENSOR_DESCRIPTIONS:
                entity_unique_id = get_host_metric_unique_id(
                    config_entry.entry_id,
                    host.host_id,
                    description.key,
                )
                current_unique_ids.add(entity_unique_id)
                if entity_unique_id in known_entities:
                    continue

                known_entities.add(entity_unique_id)
                new_entities.append(
                    MMonitHostSensor(
                        coordinator=coordinator,
                        host_id=host.host_id,
                        description=description,
                        unique_id=entity_unique_id,
                    )
                )

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


class MMonitHostSensor(MMonitHostEntity, SensorEntity):
    """Sensor representing one host-level M/Monit metric."""

    entity_description: MMonitHostSensorDescription

    def __init__(
        self,
        coordinator: MMonitDataUpdateCoordinator,
        host_id: str,
        description: MMonitHostSensorDescription,
        unique_id: str,
    ) -> None:
        """Initialize the host sensor."""
        super().__init__(coordinator, host_id)
        self.entity_description = description
        self._attr_unique_id = unique_id
        self.entity_id = suggest_entity_id(
            "sensor", coordinator, host_id, str(description.name)
        )

    @property
    def native_value(self) -> str | float | int | None:
        """Return the current host metric value."""
        host = self.host
        if host is None:
            return None
        return getattr(host, self.entity_description.value_attr)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes for host sensors that need them."""
        host = self.host
        if host is None or self.entity_description.key != HOST_SENSOR_PLATFORM:
            return {}

        attributes = {
            ATTR_SERVER_NAME: self.coordinator.server_name,
            ATTR_SERVER_URL: self.coordinator.server_url,
        }
        if host.platform_release is not None:
            attributes["platform_release"] = host.platform_release
        if host.platform_version is not None:
            attributes["platform_version"] = host.platform_version
        if host.platform_machine is not None:
            attributes["platform_machine"] = host.platform_machine
        if host.monit_version is not None:
            attributes["monit_version"] = host.monit_version
        if host.monit_uptime is not None:
            attributes["monit_uptime"] = host.monit_uptime
        return attributes


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
        host = coordinator.data.get(host_id)
        check = host.checks.get(check_id) if host else None
        self.entity_id = suggest_entity_id(
            "sensor", coordinator, host_id, check.name if check else check_id
        )

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
        if check.last_events:
            attributes[ATTR_LAST_EVENTS] = check.last_events
        if check.last_exit_value is not None:
            attributes[ATTR_LAST_EXIT_VALUE] = check.last_exit_value
        if check.port_response_time is not None:
            attributes[ATTR_PORT_RESPONSE_TIME] = check.port_response_time
        if check.data_collected is not None:
            attributes[ATTR_DATA_COLLECTED] = check.data_collected
        if self.events_url is not None:
            attributes[ATTR_EVENTS_URL] = self.events_url

        return attributes
