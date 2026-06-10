"""Data update coordinator for M/Monit."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MMonitApiClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .exceptions import MMonitApiError, MMonitAuthenticationError
from .models import MMonitHost
from .monit_api import MonitApiClient

_LOGGER = logging.getLogger(__name__)


class MMonitDataUpdateCoordinator(DataUpdateCoordinator[dict[str, MMonitHost]]):
    """Coordinate fetching all hosts and checks for one M/Monit or Monit server."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MMonitApiClient | MonitApiClient,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}_{config_entry.entry_id}",
            update_interval=timedelta(
                seconds=config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client

    @property
    def server_name(self) -> str:
        """Return the best server name."""
        return self.config_entry.title or self.client.server_name

    @property
    def server_url(self) -> str:
        """Return the configured server URL."""
        return self.client.base_url

    async def _async_update_data(self) -> dict[str, MMonitHost]:
        """Fetch data from M/Monit."""
        try:
            return await self.client.async_fetch_hosts()
        except MMonitAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except MMonitApiError as err:
            raise UpdateFailed(str(err)) from err

