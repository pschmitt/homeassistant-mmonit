"""Config flow for M/Monit."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import MMonitApiClient, normalize_url
from .const import (
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .exceptions import MMonitApiError, MMonitAuthenticationError

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate the config flow input."""
    session = async_create_clientsession(
        hass,
        verify_ssl=data[CONF_VERIFY_SSL],
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )
    client = MMonitApiClient(
        session=session,
        base_url=data[CONF_URL],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
    )

    try:
        hosts = await client.async_fetch_hosts()
    finally:
        await client.async_close()

    return {
        "title": data.get(CONF_NAME) or client.server_name,
        "unique_id": normalize_url(data[CONF_URL]),
        "host_count": str(len(hosts)),
    }


class MMonitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for M/Monit."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MMonitOptionsFlow:
        """Return the options flow for this handler."""
        return MMonitOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_URL] = normalize_url(user_input[CONF_URL])

            try:
                info = await validate_input(self.hass, user_input)
            except MMonitAuthenticationError:
                errors["base"] = "invalid_auth"
            except MMonitApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception while validating M/Monit config")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                data = {
                    CONF_URL: user_input[CONF_URL],
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                }
                options = {CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL}
                title = user_input.get(CONF_NAME) or info["title"]
                return self.async_create_entry(title=title, data=data, options=options)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL): TextSelector(),
                    vol.Optional(CONF_NAME): TextSelector(),
                    vol.Required(CONF_USERNAME): TextSelector(),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(
                        CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
        )


class MMonitOptionsFlow(OptionsFlow):
    """Handle options for M/Monit."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manage the M/Monit options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            mode=NumberSelectorMode.BOX,
                            step=1,
                        )
                    )
                }
            ),
        )
