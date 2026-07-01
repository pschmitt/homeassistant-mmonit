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
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform

from .const import (
    ATTR_ACTION_RESTART,
    ATTR_ACTION_START,
    ATTR_ACTION_STOP,
    ATTR_CHECK_GROUP,
    ATTR_CHECK_ID,
    ATTR_CHECK_PATH,
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
    ATTR_ON_REBOOT,
    ATTR_PENDING_ACTION,
    ATTR_PID,
    ATTR_PORT_RESPONSE_TIME,
    ATTR_PPID,
    ATTR_PROCESS_UPTIME,
    ATTR_RESOURCE_SUMMARY,
    ATTR_SERVER_NAME,
    ATTR_SERVER_URL,
    ATTR_STATUS_MESSAGE,
    ATTR_SYSTEM_CPU_PERCENT,
    ATTR_SYSTEM_LOAD_1,
    ATTR_SYSTEM_LOAD_5,
    ATTR_SYSTEM_LOAD_15,
    ATTR_SYSTEM_LOAD_PER_CORE,
    ATTR_SYSTEM_MEMORY_PERCENT,
    ATTR_SYSTEM_SWAP_PERCENT,
    DOMAIN,
    HOST_SENSOR_CPU_COUNT,
    HOST_SENSOR_CPU_USAGE,
    HOST_SENSOR_LOAD_1,
    HOST_SENSOR_LOAD_5,
    HOST_SENSOR_LOAD_15,
    HOST_SENSOR_MEMORY_TOTAL,
    HOST_SENSOR_MEMORY_USAGE,
    HOST_SENSOR_PLATFORM,
    HOST_SENSOR_SWAP_TOTAL,
    HOST_SENSOR_SWAP_USAGE,
    HOST_SENSOR_UPTIME,
)
from .coordinator import MMonitDataUpdateCoordinator
from .entity import MMonitEntity, MMonitHostEntity, suggest_entity_id
from .registry import get_check_unique_id, get_host_metric_unique_id


@dataclass(frozen=True, kw_only=True)
class MMonitHostSensorDescription(SensorEntityDescription):
    """Description of a host-level M/Monit sensor."""

    value_attr: str
    # When True, only create the entity for hosts that actually report the
    # value (e.g. load/swap are standalone-monit only, absent from M/Monit).
    require_value: bool = False


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
        key=HOST_SENSOR_LOAD_1,
        name="Load Average (1m)",
        icon="mdi:chart-line-variant",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_attr="load_1",
        require_value=True,
    ),
    MMonitHostSensorDescription(
        key=HOST_SENSOR_LOAD_5,
        name="Load Average (5m)",
        icon="mdi:chart-line-variant",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_attr="load_5",
        require_value=True,
    ),
    MMonitHostSensorDescription(
        key=HOST_SENSOR_LOAD_15,
        name="Load Average (15m)",
        icon="mdi:chart-line-variant",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_attr="load_15",
        require_value=True,
    ),
    MMonitHostSensorDescription(
        key=HOST_SENSOR_SWAP_USAGE,
        name="Swap Usage",
        icon="mdi:harddisk",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_attr="swap",
        require_value=True,
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
                if (
                    description.require_value
                    and getattr(host, description.value_attr) is None
                ):
                    continue
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

    platform = async_get_current_platform()
    for _svc, _action in (
        ("start_service", "start"),
        ("stop_service", "stop"),
        ("restart_service", "restart"),
        ("monitor_service", "monitor"),
        ("unmonitor_service", "unmonitor"),
    ):
        platform.async_register_entity_service(_svc, {}, f"async_{_svc}")


class MMonitHostSensor(MMonitHostEntity, SensorEntity):
    """Sensor representing one host-level M/Monit metric."""

    # monit_uptime increments on every poll and would otherwise force a new
    # state row each cycle. Keep it live but exclude it from the recorder.
    _unrecorded_attributes = frozenset({"monit_uptime"})

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

    # These attributes change on (almost) every poll and/or are large
    # (last_output can be multi-line check output). The check status itself
    # rarely changes, so recording these forced a new state row + unique
    # attribute blob every cycle and dominated recorder DB growth. Keep them
    # live for the UI but never persist them to history.
    _unrecorded_attributes = frozenset(
        {
            ATTR_LAST_OUTPUT,
            ATTR_LAST_EVENTS,
            ATTR_PORT_RESPONSE_TIME,
            ATTR_DATA_COLLECTED,
            ATTR_PROCESS_UPTIME,
            # Live system readings change every poll; keep them out of history.
            ATTR_RESOURCE_SUMMARY,
            ATTR_SYSTEM_LOAD_1,
            ATTR_SYSTEM_LOAD_5,
            ATTR_SYSTEM_LOAD_15,
            ATTR_SYSTEM_LOAD_PER_CORE,
            ATTR_SYSTEM_CPU_PERCENT,
            ATTR_SYSTEM_MEMORY_PERCENT,
            ATTR_SYSTEM_SWAP_PERCENT,
        }
    )

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
        if check.check_path is not None:
            attributes[ATTR_CHECK_PATH] = check.check_path
        if check.check_group is not None:
            attributes[ATTR_CHECK_GROUP] = check.check_group
        if check.action_start is not None:
            attributes[ATTR_ACTION_START] = check.action_start
        if check.action_stop is not None:
            attributes[ATTR_ACTION_STOP] = check.action_stop
        if check.action_restart is not None:
            attributes[ATTR_ACTION_RESTART] = check.action_restart
        if check.on_reboot is not None:
            attributes[ATTR_ON_REBOOT] = check.on_reboot
        if check.pending_action is not None:
            attributes[ATTR_PENDING_ACTION] = check.pending_action
        if check.pid is not None:
            attributes[ATTR_PID] = check.pid
        if check.ppid is not None:
            attributes[ATTR_PPID] = check.ppid
        if check.process_uptime is not None:
            attributes[ATTR_PROCESS_UPTIME] = check.process_uptime
        if check.resource_summary is not None:
            attributes[ATTR_RESOURCE_SUMMARY] = check.resource_summary
        if check.system_load_1 is not None:
            attributes[ATTR_SYSTEM_LOAD_1] = check.system_load_1
        if check.system_load_5 is not None:
            attributes[ATTR_SYSTEM_LOAD_5] = check.system_load_5
        if check.system_load_15 is not None:
            attributes[ATTR_SYSTEM_LOAD_15] = check.system_load_15
        if check.system_load_per_core is not None:
            attributes[ATTR_SYSTEM_LOAD_PER_CORE] = check.system_load_per_core
        if check.system_cpu_percent is not None:
            attributes[ATTR_SYSTEM_CPU_PERCENT] = check.system_cpu_percent
        if check.system_memory_percent is not None:
            attributes[ATTR_SYSTEM_MEMORY_PERCENT] = check.system_memory_percent
        if check.system_swap_percent is not None:
            attributes[ATTR_SYSTEM_SWAP_PERCENT] = check.system_swap_percent

        return attributes

    async def async_start_service(self) -> None:
        """Start this monitored service."""
        await self._async_monit_action("start")

    async def async_stop_service(self) -> None:
        """Stop this monitored service."""
        await self._async_monit_action("stop")

    async def async_restart_service(self) -> None:
        """Restart this monitored service."""
        await self._async_monit_action("restart")

    async def async_monitor_service(self) -> None:
        """Enable monitoring for this service."""
        await self._async_monit_action("monitor")

    async def async_unmonitor_service(self) -> None:
        """Disable monitoring for this service."""
        await self._async_monit_action("unmonitor")

    async def _async_monit_action(self, action: str) -> None:
        await self.coordinator.client.async_action(
            self._host_id, self._check_id, action
        )
        await self.coordinator.async_request_refresh()
