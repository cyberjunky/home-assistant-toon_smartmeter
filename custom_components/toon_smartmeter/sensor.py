"""Sensor for Toon Smart Meter integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_NAME,
    DOMAIN,
    SENSOR_TYPES,
)
from .coordinator import ToonSmartMeterCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Toon Smart Meter sensors from a config entry."""
    coordinator: ToonSmartMeterCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Create all sensor entities
    entities = []
    for description in SENSOR_TYPES:
        entities.append(
            ToonSmartMeterSensor(
                coordinator=coordinator,
                description=description,
                entry=entry,
            )
        )
        _LOGGER.debug("Adding Toon Smart Meter sensor: %s", description.name)

    async_add_entities(entities)


class ToonSmartMeterSensor(CoordinatorEntity[ToonSmartMeterCoordinator], SensorEntity):
    """Representation of a Toon Smart Meter sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ToonSmartMeterCoordinator,
        description: SensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        # Get device name from options (with fallback to data for migration)
        device_name = entry.options.get(CONF_NAME) or entry.data.get(CONF_NAME, DEFAULT_NAME)

        # Set device info for grouping
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{device_name} Smart Meter",
            manufacturer="Eneco",
            model="Toon Thermostat",
            configuration_url=f"http://{coordinator.host}:{coordinator.port}",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.get_sensor_value(self.entity_description.key)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        # Check if this sensor's device has been discovered
        sensor_key = self.entity_description.key

        # Pulse sensors don't have a device_id mapping
        if sensor_key in ["elecusageflowpulse", "elecusagecntpulse"]:
            return sensor_key in self.coordinator.device_ids

        # Solar sensors may use export devices
        if sensor_key in ["elecsolar", "elecsolarcnt"]:
            # Available if we have the device OR if export devices exist
            if sensor_key in self.coordinator.device_ids:
                return True
            if self.coordinator.data:
                for dev in ["dev_4.export", "dev_3.export", "dev_7.export", "dev_14.export"]:
                    if dev in self.coordinator.data:
                        return True
            return False

        # For other sensors, check if device was discovered
        return sensor_key in self.coordinator.device_ids
