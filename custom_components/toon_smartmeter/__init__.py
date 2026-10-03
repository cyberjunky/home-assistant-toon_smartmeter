"""Toon Smart Meter integration for Home Assistant."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SENSOR_MAP,
)
from .coordinator import ToonSmartMeterCoordinator

if TYPE_CHECKING:
    from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

# Schema for YAML configuration (legacy support for migration)
SENSOR_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.positive_int,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional("sensor"): vol.All(cv.ensure_list, [SENSOR_SCHEMA]),
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


# Pre-2.0 releases always used a hardcoded "Toon " prefix (the old YAML schema
# had no CONF_NAME option for this integration) and built unique_id from the
# sensor's display name, e.g. unique_id="Toon _Gas Used Cnt" for
# entity_id="sensor.toon_gas_used_cnt". Two sensors were renamed since; every
# other name is unchanged.
LEGACY_UNIQUE_ID_PREFIX = "Toon "
LEGACY_SENSOR_NAME_OVERRIDES: dict[str, str] = {
    "waterquantity": "P1 waterquantity",
    "waterflow": "P1 waterflow",
}


async def async_migrate_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate pre-2.0 entities to the current unique_id format.

    Renaming the unique_id lets the entity registry reuse the existing
    entity_id instead of registering a new one, so Home Assistant's recorder
    keeps the entity's history and long-term statistics intact.
    """
    entity_registry = er.async_get(hass)
    host = entry.data.get(CONF_HOST)
    migrated_count = 0

    for sensor_key, description in SENSOR_MAP.items():
        new_unique_id = f"{entry.entry_id}_{sensor_key}"

        # Already migrated / already on the new scheme.
        if entity_registry.async_get_entity_id("sensor", DOMAIN, new_unique_id):
            continue

        legacy_name = LEGACY_SENSOR_NAME_OVERRIDES.get(sensor_key, description.name)
        old_unique_id = f"{LEGACY_UNIQUE_ID_PREFIX}_{legacy_name}"

        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, old_unique_id)
        if not entity_id:
            continue

        _LOGGER.info(
            "Migrating entity %s from legacy unique_id '%s' to '%s'",
            entity_id,
            old_unique_id,
            new_unique_id,
        )
        entity_registry.async_update_entity(
            entity_id,
            new_unique_id=new_unique_id,
            config_entry_id=entry.entry_id,
        )
        migrated_count += 1

    if migrated_count > 0:
        _LOGGER.info("Migrated %s entities for host %s", migrated_count, host)
    else:
        _LOGGER.debug("No legacy entities found to migrate for host %s", host)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Toon Smart Meter integration from YAML (legacy migration)."""
    hass.data.setdefault(DOMAIN, {})

    # Check for legacy sensor platform configuration
    if "sensor" in config:
        for platform_config in config["sensor"]:
            if platform_config.get("platform") == DOMAIN:
                _LOGGER.warning(
                    "Configuration of Toon Smart Meter via YAML platform is deprecated. "
                    "Your configuration has been imported. Please remove the YAML "
                    "configuration and restart Home Assistant."
                )
                # Import the configuration
                hass.async_create_task(
                    hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": "import"},
                        data=platform_config,
                    )
                )

    # Check for new-style domain configuration
    if DOMAIN in config:
        domain_config = config[DOMAIN]
        if "sensor" in domain_config:
            for sensor_config in domain_config["sensor"]:
                _LOGGER.warning(
                    "Configuration of Toon Smart Meter via YAML is deprecated. "
                    "Your configuration has been imported. Please remove the YAML "
                    "configuration and restart Home Assistant."
                )
                hass.async_create_task(
                    hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": "import"},
                        data=sensor_config,
                    )
                )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Toon Smart Meter from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Migrate old entities to new unique_id format
    await async_migrate_entities(hass, entry)

    session = async_get_clientsession(hass)

    # Get configuration - host/port from data, user preferences from options
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    # Create coordinator
    coordinator = ToonSmartMeterCoordinator(
        hass=hass,
        session=session,
        host=host,
        port=port,
        scan_interval=scan_interval,
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", entry.version)

    # Currently at version 1, so no migration needed yet
    # This is a placeholder for future migrations
    if entry.version == 1:
        # No migration needed
        pass

    _LOGGER.info("Migration to version %s successful", entry.version)
    return True
