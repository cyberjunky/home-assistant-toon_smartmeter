"""Config flow for Toon Smart Meter integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import async_timeout
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    BASE_URL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def validate_connection(hass: HomeAssistant, host: str, port: int) -> dict[str, Any]:
    """Validate the connection to Toon device."""
    session = async_get_clientsession(hass)
    url = BASE_URL.format(host, port)

    try:
        async with async_timeout.timeout(10):
            response = await session.get(url, headers={"Accept-Encoding": "identity"})
            response.raise_for_status()
            data = await response.json(content_type="text/javascript")
            _LOGGER.debug("Connection test successful: %s", data)
            return {"title": f"Toon {host}"}
    except aiohttp.ClientError as err:
        _LOGGER.error("Cannot connect to Toon at %s: %s", url, err)
        raise ConnectionError(f"Cannot connect to Toon: {err}") from err
    except TimeoutError as err:
        _LOGGER.error("Timeout connecting to Toon at %s", url)
        raise ConnectionError("Timeout connecting to Toon") from err
    except (TypeError, KeyError, ValueError) as err:
        _LOGGER.error("Invalid data from Toon at %s: %s", url, err)
        raise ValueError(f"Invalid data from Toon: {err}") from err


class ToonSmartMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Toon Smart Meter."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_connection(
                    self.hass, user_input[CONF_HOST], user_input[CONF_PORT]
                )
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "invalid_data"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create unique ID based on host
                await self.async_set_unique_id(user_input[CONF_HOST])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, info["title"]),
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_PORT: user_input[CONF_PORT],
                    },
                    options={
                        CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                        CONF_SCAN_INTERVAL: user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.positive_int,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): cv.positive_int,
                }
            ),
            errors=errors,
        )

    async def async_step_import(self, import_config: dict[str, Any]) -> FlowResult:
        """Handle import from YAML configuration."""
        _LOGGER.info("Importing Toon Smart Meter configuration from YAML")

        # Check if already configured
        await self.async_set_unique_id(import_config[CONF_HOST])
        self._abort_if_unique_id_configured()

        try:
            await validate_connection(
                self.hass,
                import_config[CONF_HOST],
                import_config.get(CONF_PORT, DEFAULT_PORT),
            )
        except (ConnectionError, ValueError):
            _LOGGER.error(
                "Failed to import YAML config - cannot connect to %s",
                import_config[CONF_HOST],
            )
            return self.async_abort(reason="cannot_connect")

        return self.async_create_entry(
            title=import_config.get(CONF_NAME, DEFAULT_NAME),
            data={
                CONF_HOST: import_config[CONF_HOST],
                CONF_PORT: import_config.get(CONF_PORT, DEFAULT_PORT),
            },
            options={
                CONF_NAME: import_config.get(CONF_NAME, DEFAULT_NAME),
                CONF_SCAN_INTERVAL: import_config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ToonSmartMeterOptionsFlow:
        """Get the options flow for this handler."""
        return ToonSmartMeterOptionsFlow()


class ToonSmartMeterOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Toon Smart Meter."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NAME,
                        default=self.config_entry.options.get(CONF_NAME, DEFAULT_NAME),
                    ): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): cv.positive_int,
                }
            ),
        )
