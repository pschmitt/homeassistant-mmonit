"""Registry helpers for dynamic M/Monit entities."""

from __future__ import annotations

from collections.abc import Mapping

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN, HOST_SENSOR_KEYS
from .entity import iter_host_device_identifiers
from .models import MMonitHost


def get_check_unique_id(
    entry_id: str,
    host_id: str,
    check_id: str,
) -> str:
    """Return the stable unique ID for one M/Monit check entity."""
    return f"{entry_id}_{host_id}_{check_id}"


def get_host_status_unique_id(entry_id: str, host_id: str) -> str:
    """Return the stable unique ID for one M/Monit host status entity."""
    return f"host_status_{entry_id}_{host_id}"


def get_host_metric_unique_id(entry_id: str, host_id: str, metric_key: str) -> str:
    """Return the stable unique ID for one M/Monit host metric entity."""
    return f"host_metric_{entry_id}_{host_id}_{metric_key}"


@callback
def async_cleanup_registry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    hosts: Mapping[str, MMonitHost],
) -> None:
    """Remove stale M/Monit entities and devices from the registries."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    current_unique_ids = {
        get_host_status_unique_id(config_entry.entry_id, host.host_id)
        for host in hosts.values()
    }
    current_unique_ids.update(
        get_host_metric_unique_id(config_entry.entry_id, host.host_id, metric_key)
        for host in hosts.values()
        for metric_key in HOST_SENSOR_KEYS
    )
    current_unique_ids.update(
        get_check_unique_id(config_entry.entry_id, host.host_id, check.service_id)
        for host in hosts.values()
        for check in host.checks.values()
    )

    valid_prefixes = (
        f"{config_entry.entry_id}_",
        f"host_status_{config_entry.entry_id}_",
        f"host_metric_{config_entry.entry_id}_",
    )
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        config_entry.entry_id,
    ):
        if entity_entry.platform != DOMAIN or not entity_entry.unique_id:
            continue
        if entity_entry.unique_id in current_unique_ids:
            continue
        if not entity_entry.unique_id.startswith(valid_prefixes):
            continue
        entity_registry.async_remove(entity_entry.entity_id)

    current_host_identifiers = iter_host_device_identifiers(
        config_entry.entry_id,
        hosts.keys(),
    )
    for device_entry in dr.async_entries_for_config_entry(
        device_registry,
        config_entry.entry_id,
    ):
        mmonit_identifiers = {
            identifier
            for identifier in device_entry.identifiers
            if identifier[0] == DOMAIN
            and identifier[1].startswith(f"{config_entry.entry_id}:")
        }
        if not mmonit_identifiers:
            continue
        if any(identifier in current_host_identifiers for identifier in mmonit_identifiers):
            continue
        device_registry.async_remove_device(device_entry.id)
