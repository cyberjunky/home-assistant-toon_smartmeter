"""Sensor for Toon Smart Meter integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfEnergy, UnitOfPower
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

    # Create all standard sensor entities
    entities: list[SensorEntity] = []
    for description in SENSOR_TYPES:
        entities.append(
            ToonSmartMeterSensor(
                coordinator=coordinator,
                description=description,
                entry=entry,
            )
        )
        _LOGGER.debug("Adding Toon Smart Meter sensor: %s", description.name)

    # Create sensors for each discovered Z-Wave plug
    for plug_id, plug_info in coordinator.zwave_plugs.items():
        plug_name = plug_info.get("name", plug_id)

        # Power sensor (current flow in Watts)
        entities.append(
            ToonZWavePlugSensor(
                coordinator=coordinator,
                entry=entry,
                plug_id=plug_id,
                plug_info=plug_info,
                sensor_type="power",
            )
        )

        # Energy sensor (total consumption in kWh)
        entities.append(
            ToonZWavePlugSensor(
                coordinator=coordinator,
                entry=entry,
                plug_id=plug_id,
                plug_info=plug_info,
                sensor_type="energy",
            )
        )
        _LOGGER.debug("Adding Z-Wave plug sensors for: %s", plug_name)

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


class ToonZWavePlugSensor(CoordinatorEntity[ToonSmartMeterCoordinator], SensorEntity):
    """Representation of a Toon Z-Wave power plug sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ToonSmartMeterCoordinator,
        entry: ConfigEntry,
        plug_id: str,
        plug_info: dict[str, Any],
        sensor_type: str,
    ) -> None:
        """Initialize the sensor.

        Args:
            coordinator: The data coordinator
            entry: Config entry
            plug_id: Device ID (e.g., "dev_4")
            plug_info: Plug info dict with name, uuid, type, internal_address
            sensor_type: Either "power" or "energy"
        """
        super().__init__(coordinator)

        self._plug_id = plug_id
        self._plug_info = plug_info
        self._sensor_type = sensor_type
        self._entry = entry

        plug_name = plug_info.get("name", plug_id)

        if sensor_type == "power":
            self._attr_name = f"{plug_name} Power"
            self._attr_unique_id = f"{entry.entry_id}_plug_{plug_id}_power"
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:flash"
        else:  # energy
            self._attr_name = f"{plug_name} Energy"
            self._attr_unique_id = f"{entry.entry_id}_plug_{plug_id}_energy"
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_icon = "mdi:lightning-bolt"

        # Get device name from options (with fallback to data for migration)
        device_name = entry.options.get(CONF_NAME) or entry.data.get(CONF_NAME, DEFAULT_NAME)

        # Set device info for grouping with main Toon device
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
        if self._sensor_type == "power":
            return self.coordinator.get_plug_power(self._plug_id)
        return self.coordinator.get_plug_energy(self._plug_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        return self._plug_id in self.coordinator.zwave_plugs

