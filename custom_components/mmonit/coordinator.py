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

# Number of consecutive updates a host may be missing before it's treated as
# genuinely removed. A single failed per-host detail fetch drops the host from
# one poll's result; without this grace the cleanup listener would delete its
# device + entities (losing customizations and history) only to recreate them
# on the next successful poll.
_MISSING_GRACE = 3


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
        self._missing_strikes: dict[str, int] = {}

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
            fresh = await self.client.async_fetch_hosts()
        except MMonitAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except MMonitApiError as err:
            raise UpdateFailed(str(err)) from err

        return self._backfill_transient_hosts(fresh)

    def _backfill_transient_hosts(
        self, fresh: dict[str, MMonitHost]
    ) -> dict[str, MMonitHost]:
        """Keep recently-seen hosts that vanished, until they've been gone a while.

        A per-host detail fetch can fail transiently, dropping that host from a
        single poll. Carry its last-known data forward for up to _MISSING_GRACE
        consecutive misses so the registry cleanup doesn't churn its device and
        entities; drop it once it stays gone (a genuine removal).
        """
        previous = self.data or {}
        merged = dict(fresh)
        for host_id, host in previous.items():
            if host_id in fresh:
                self._missing_strikes.pop(host_id, None)
                continue
            strikes = self._missing_strikes.get(host_id, 0) + 1
            if strikes < _MISSING_GRACE:
                self._missing_strikes[host_id] = strikes
                merged[host_id] = host
                _LOGGER.debug(
                    "Host %s missing from M/Monit result (%d/%d), keeping last data",
                    host_id,
                    strikes,
                    _MISSING_GRACE,
                )
            else:
                self._missing_strikes.pop(host_id, None)
                _LOGGER.debug("Host %s gone for %d updates, dropping", host_id, strikes)
        return merged

