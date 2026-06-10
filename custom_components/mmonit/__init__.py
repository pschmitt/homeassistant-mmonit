"""The M/Monit integration."""

from __future__ import annotations

from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import MMonitApiClient
from .const import CONF_MODE, CONF_VERIFY_SSL, DOMAIN, MODE_MMONIT, MODE_MONIT, PLATFORMS
from .coordinator import MMonitDataUpdateCoordinator
from .monit_api import MonitApiClient
from .registry import async_cleanup_registry


def create_client(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> MMonitApiClient | MonitApiClient:
    """Create the right API client for the configured mode."""
    mode = data.get(CONF_MODE, MODE_MMONIT)
    session = async_create_clientsession(
        hass,
        verify_ssl=data[CONF_VERIFY_SSL],
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )
    client_class = MonitApiClient if mode == MODE_MONIT else MMonitApiClient
    return client_class(
        session=session,
        base_url=data[CONF_URL],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
    )


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the M/Monit integration."""
    del config
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up M/Monit from a config entry."""
    client = create_client(hass, dict(config_entry.data))
    coordinator = MMonitDataUpdateCoordinator(hass, client, config_entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][config_entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    async_cleanup_registry(hass, config_entry, coordinator.data)

    @callback
    def async_cleanup_listener() -> None:
        """Remove stale entities and devices after coordinator updates."""
        async_cleanup_registry(hass, config_entry, coordinator.data)

    config_entry.async_on_unload(coordinator.async_add_listener(async_cleanup_listener))
    config_entry.async_on_unload(config_entry.add_update_listener(async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload an M/Monit config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(config_entry.entry_id)
        await runtime["client"].async_close()
    return unload_ok


async def async_update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Reload the integration after options changes."""
    await hass.config_entries.async_reload(config_entry.entry_id)
