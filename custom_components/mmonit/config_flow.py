"""Config flow for M/Monit."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import create_client
from .api import normalize_url
from .const import (
    CONF_MODE,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    MODE_MMONIT,
    MODE_MONIT,
)
from .exceptions import MMonitApiError, MMonitAuthenticationError

_LOGGER = logging.getLogger(__name__)

ADD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(),
        vol.Optional(CONF_NAME): TextSelector(),
        vol.Required(CONF_USERNAME): TextSelector(),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): BooleanSelector(),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate the config flow input."""
    client = create_client(hass, data)

    try:
        hosts = await client.async_fetch_hosts()
    finally:
        await client.async_close()

    default_title = client.server_name
    if data.get(CONF_MODE, MODE_MMONIT) == MODE_MONIT and hosts:
        default_title = next(iter(hosts.values())).display_name

    return {
        "title": data.get(CONF_NAME) or default_title,
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
        """Let the user pick between an M/Monit server and a direct Monit agent."""
        del user_input
        return self.async_show_menu(
            step_id="user",
            menu_options=[MODE_MMONIT, MODE_MONIT],
        )

    async def async_step_mmonit(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle adding an M/Monit server."""
        return await self._async_step_add(MODE_MMONIT, user_input)

    async def async_step_monit(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle adding a Monit agent directly."""
        return await self._async_step_add(MODE_MONIT, user_input)

    async def _async_step_add(
        self,
        mode: str,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        """Handle adding one M/Monit server or Monit agent."""
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_URL] = normalize_url(user_input[CONF_URL])
            user_input[CONF_MODE] = mode

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
                    CONF_MODE: mode,
                    CONF_URL: user_input[CONF_URL],
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
                }
                options = {CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL}
                title = user_input.get(CONF_NAME) or info["title"]
                return self.async_create_entry(title=title, data=data, options=options)

        return self.async_show_form(
            step_id=mode,
            data_schema=ADD_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            user_input[CONF_URL] = normalize_url(user_input[CONF_URL])
            # An empty password means: keep the current one
            if not user_input.get(CONF_PASSWORD):
                user_input[CONF_PASSWORD] = entry.data[CONF_PASSWORD]
            data = {**entry.data, **user_input}

            try:
                info = await validate_input(self.hass, data)
            except MMonitAuthenticationError:
                errors["base"] = "invalid_auth"
            except MMonitApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception while validating M/Monit config")
                errors["base"] = "unknown"
            else:
                new_unique_id = info["unique_id"]
                for other in self._async_current_entries():
                    if (
                        other.entry_id != entry.entry_id
                        and other.unique_id == new_unique_id
                    ):
                        return self.async_abort(reason="already_configured")
                return self.async_update_reload_and_abort(
                    entry,
                    data=data,
                    unique_id=new_unique_id,
                )

        defaults = user_input or entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_URL, default=defaults.get(CONF_URL, "")
                    ): TextSelector(),
                    vol.Required(
                        CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")
                    ): TextSelector(),
                    vol.Optional(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(
                        CONF_VERIFY_SSL,
                        default=defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
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
