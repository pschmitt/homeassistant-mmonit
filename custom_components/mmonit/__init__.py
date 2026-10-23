"""The M/Monit integration."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import MMonitApiClient
from .const import (
    CONF_API_TOKEN,
    CONF_MODE,
    CONF_VERIFY_SSL,
    DOMAIN,
    MODE_MMONIT,
    MODE_MONARCH,
    MODE_MONIT,
    PLATFORMS,
)
from .coordinator import MMonitDataUpdateCoordinator
from .monarch_api import MonarchApiClient
from .monit_api import MonitApiClient
from .registry import async_cleanup_registry

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_URL = f"/{DOMAIN}/monit-strategy.js"
CARD_PATH = Path(__file__).parent / "frontend" / "monit-strategy.js"
LEGACY_CARD_URL = f"/local/{CARD_PATH.name}"


def create_client(
    hass: HomeAssistant,
    data: dict[str, Any],
) -> MMonitApiClient | MonitApiClient | MonarchApiClient:
    """Create the right API client for the configured mode."""
    mode = data.get(CONF_MODE, MODE_MMONIT)
    session = async_create_clientsession(
        hass,
        verify_ssl=data[CONF_VERIFY_SSL],
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )
    if mode == MODE_MONARCH:
        return MonarchApiClient(
            session=session,
            base_url=data[CONF_URL],
            username="",
            password=data[CONF_API_TOKEN],
        )
    client_class = MonitApiClient if mode == MODE_MONIT else MMonitApiClient
    return client_class(
        session=session,
        base_url=data[CONF_URL],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the M/Monit integration, serve strategy and register resource."""
    del config
    hass.data.setdefault(DOMAIN, {})

    if CARD_PATH.exists():
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=False)]
        )
        digest = await hass.async_add_executor_job(
            lambda: hashlib.sha256(CARD_PATH.read_bytes()).hexdigest()[:10]
        )
        await _async_register_card(hass, f"{CARD_URL}?v={digest}")

    return True


async def _async_register_card(hass: HomeAssistant, url: str) -> None:
    """Keep exactly one Lovelace resource pointing at the current strategy."""
    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None or lovelace.resource_mode != "storage":
        add_extra_js_url(hass, url)
        return
    resources = lovelace.resources
    await resources.async_get_info()  # loads the collection

    # Remove legacy /local/ resource if present
    legacy = [
        item for item in resources.async_items() if item["url"].split("?")[0] == LEGACY_CARD_URL
    ]
    for old in legacy:
        await resources.async_delete_item(old["id"])

    mine = [item for item in resources.async_items() if item["url"].split("?")[0] == CARD_URL]
    for duplicate in mine[1:]:
        await resources.async_delete_item(duplicate["id"])
    if not mine:
        _LOGGER.info("Adding M/Monit strategy as a dashboard resource")
        await resources.async_create_item({"res_type": "module", "url": url})
    elif mine[0]["url"] != url:
        await resources.async_update_item(mine[0]["id"], {"res_type": "module", "url": url})


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up M/Monit from a config entry."""
    client = create_client(hass, dict(config_entry.data))
    coordinator = MMonitDataUpdateCoordinator(hass, client, config_entry)

    hass.data[DOMAIN][config_entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    if coordinator.data is None:
        coordinator.last_update_success = False
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    @callback
    def async_cleanup_listener() -> None:
        """Remove stale entities and devices after coordinator updates."""
        if coordinator.last_update_success and coordinator.data is not None:
            async_cleanup_registry(hass, config_entry, coordinator.data)

    config_entry.async_on_unload(coordinator.async_add_listener(async_cleanup_listener))
    config_entry.async_on_unload(config_entry.add_update_listener(async_update_listener))
    config_entry.async_create_background_task(
        hass, coordinator.async_refresh(), "mmonit_first_refresh"
    )
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
