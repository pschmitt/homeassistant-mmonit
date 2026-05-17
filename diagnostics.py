"""Diagnostics support for M/Monit."""

from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> dict:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    hosts = []
    for host in coordinator.data.values():
        hosts.append(
            {
                "host_id": host.host_id,
                "name": host.display_name,
                "summary": host.summary,
                "check_count": len(host.checks),
                "checks": [
                    {
                        "service_id": check.service_id,
                        "name": check.name,
                        "status": check.status,
                        "message": check.message,
                    }
                    for check in host.checks.values()
                ],
            }
        )

    return {
        "entry": async_redact_data(dict(config_entry.data), TO_REDACT),
        "options": dict(config_entry.options),
        "hosts": hosts,
    }
