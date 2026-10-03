"""Config flow for Toon Smart Meter integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    BASE_URL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL_VALIDATOR = vol.All(vol.Coerce(int), vol.Range(min=1))


async def validate_connection(hass: HomeAssistant, host: str, port: int) -> None:
    """Validate the connection to Toon device."""
    session = async_get_clientsession(hass)
    url = BASE_URL.format(host, port)

    try:
        async with asyncio.timeout(10):
            response = await session.get(url, headers={"Accept-Encoding": "identity"})
            response.raise_for_status()
            data = await response.json(content_type="text/javascript")
            _LOGGER.debug("Connection test successful: %s", data)
    except aiohttp.ClientError as err:
        _LOGGER.debug("Cannot connect to Toon at %s: %s", url, err)
        raise ConnectionError(f"Cannot connect to Toon: {err}") from err
    except TimeoutError as err:
        _LOGGER.debug("Timeout connecting to Toon at %s", url)
        raise ConnectionError("Timeout connecting to Toon") from err
    except (TypeError, KeyError, ValueError) as err:
        _LOGGER.debug("Invalid data from Toon at %s: %s", url, err)
        raise ValueError(f"Invalid data from Toon: {err}") from err


async def _async_validate(hass: HomeAssistant, host: str, port: int) -> str | None:
    """Validate the connection and return an error key, or None on success."""
    try:
        await validate_connection(hass, host, port)
    except ConnectionError:
        return "cannot_connect"
    except ValueError:
        return "invalid_data"
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected exception")
        return "unknown"
    return None


class ToonSmartMeterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Toon Smart Meter."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            name = user_input.get(CONF_NAME, DEFAULT_NAME)

            # Set unique ID based on host to prevent duplicates
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            if error := await _async_validate(self.hass, host, port):
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                    },
                    options={
                        CONF_NAME: name,
                        CONF_SCAN_INTERVAL: user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                        vol.Optional(
                            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                        ): SCAN_INTERVAL_VALIDATOR,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle import from YAML configuration."""
        host = import_data.get(CONF_HOST)
        if not host:
            return self.async_abort(reason="invalid_import")
        port = import_data.get(CONF_PORT, DEFAULT_PORT)
        name = import_data.get(CONF_NAME, DEFAULT_NAME)

        # Check if already configured
        await self.async_set_unique_id(host)
        self._abort_if_unique_id_configured()

        _LOGGER.info("Importing Toon Smart Meter configuration from YAML for host: %s", host)

        if await _async_validate(self.hass, host, port):
            _LOGGER.error("Failed to import YAML config - cannot connect to %s", host)
            return self.async_abort(reason="cannot_connect")

        return self.async_create_entry(
            title=name,
            data={
                CONF_HOST: host,
                CONF_PORT: port,
            },
            options={
                CONF_NAME: name,
                CONF_SCAN_INTERVAL: import_data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return ToonSmartMeterOptionsFlow()


class ToonSmartMeterOptionsFlow(OptionsFlowWithReload):
    """Handle options flow for Toon Smart Meter."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        entry = self.config_entry

        if user_input is not None:
            current_host = entry.data[CONF_HOST]
            current_port = entry.data.get(CONF_PORT, DEFAULT_PORT)
            current_name = entry.options.get(CONF_NAME) or entry.data.get(CONF_NAME, DEFAULT_NAME)
            new_host = user_input[CONF_HOST].strip()
            new_port = user_input.get(CONF_PORT, current_port)
            new_name = user_input.get(CONF_NAME, current_name)
            address_changed = new_host != current_host or new_port != current_port

            if new_host != current_host and any(
                other.entry_id != entry.entry_id and other.unique_id == new_host
                for other in self.hass.config_entries.async_entries(DOMAIN)
            ):
                errors["base"] = "already_configured"
            elif address_changed and (
                error := await _async_validate(self.hass, new_host, new_port)
            ):
                errors["base"] = error

            if not errors:
                updates: dict[str, Any] = {}
                if address_changed:
                    updates["unique_id"] = new_host
                    updates["data"] = {**entry.data, CONF_HOST: new_host, CONF_PORT: new_port}
                # Keep the entry title in sync with the name, unless it was renamed manually
                if new_name != current_name and entry.title == current_name:
                    updates["title"] = new_name
                if updates:
                    self.hass.config_entries.async_update_entry(entry, **updates)

                new_options = {
                    CONF_NAME: new_name,
                    CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                }
                # OptionsFlowWithReload only reloads when the options change, so a
                # host/port-only change must schedule the reload itself. This also
                # cancels a pending setup retry that would still use the old address.
                if address_changed and new_options == dict(entry.options):
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)

                return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(self._get_options_schema(), user_input),
            errors=errors,
        )

    def _get_options_schema(self) -> vol.Schema:
        """Return the options schema."""
        data = self.config_entry.data
        options = self.config_entry.options
        return vol.Schema(
            {
                vol.Required(CONF_HOST, default=data[CONF_HOST]): str,
                vol.Optional(CONF_PORT, default=data.get(CONF_PORT, DEFAULT_PORT)): cv.port,
                vol.Optional(
                    CONF_NAME,
                    default=options.get(CONF_NAME) or data.get(CONF_NAME, DEFAULT_NAME),
                ): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): SCAN_INTERVAL_VALIDATOR,
            }
        )
