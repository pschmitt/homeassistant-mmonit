"""The M/Monit integration."""

from __future__ import annotations

from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import MMonitApiClient
from .const import CONF_VERIFY_SSL, DOMAIN, PLATFORMS
from .coordinator import MMonitDataUpdateCoordinator


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the M/Monit integration."""
    del config
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up M/Monit from a config entry."""
    session = async_create_clientsession(
        hass,
        verify_ssl=config_entry.data[CONF_VERIFY_SSL],
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )
    client = MMonitApiClient(
        session=session,
        base_url=config_entry.data[CONF_URL],
        username=config_entry.data[CONF_USERNAME],
        password=config_entry.data[CONF_PASSWORD],
    )
    coordinator = MMonitDataUpdateCoordinator(hass, client, config_entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][config_entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    config_entry.async_on_unload(config_entry.add_update_listener(async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload an M/Monit config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    runtime = hass.data[DOMAIN].pop(config_entry.entry_id)
    await runtime["client"].async_close()
    return unload_ok


async def async_update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Reload the integration after options changes."""
    await hass.config_entries.async_reload(config_entry.entry_id)
