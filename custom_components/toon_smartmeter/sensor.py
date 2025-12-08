"""Sensor for Toon Smart Meter integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from functools import reduce
import logging
from typing import Final

import aiohttp
import async_timeout
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorStateClass,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_RESOURCES,
    PERCENTAGE,
    UnitOfPower,
    UnitOfEnergy,
    UnitOfVolume,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

BASE_URL = "http://{0}:{1}/hdrv_zwave?action=getDevices.json"

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=10)

SENSOR_PREFIX = "Toon "
SENSOR_LIST = {
    "gasused",
    "gasusedcnt",
    "elecusageflowpulse",
    "elecusagecntpulse",
    "elecusageflowlow",
    "elecusageflowhigh",
    "elecprodflowlow",
    "elecprodflowhigh",
    "elecusagecntlow",
    "elecusagecnthigh",
    "elecprodcntlow",
    "elecprodcnthigh",
    "elecsolar",
    "elecsolarcnt",
    "heat",
    "waterflow",
    "waterquantity",
}

SENSOR_TYPES: Final[tuple[SensorEntityDescription, ...]] = (
    SensorEntityDescription(
        key="gasused",
        name="Gas Used Last Hour",
        icon="mdi:gas-cylinder",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="gasusedcnt",
        name="Gas Used Cnt",
        icon="mdi:gas-cylinder",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecusageflowpulse",
        name="Power Use",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    SensorEntityDescription(
        key="elecusageflowlow",
        name="P1 Power Use Low",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="elecusageflowhigh",
        name="P1 Power Use High",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="elecprodflowlow",
        name="P1 Power Prod Low",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="elecprodflowhigh",
        name="P1 Power Prod High",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="elecusagecntpulse",
        name="P1 Power Use Cnt",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecusagecntlow",
        name="P1 Power Use Cnt Low",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecusagecnthigh",
        name="P1 Power Use Cnt High",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecprodcntlow",
        name="P1 Power Prod Cnt Low",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecprodcnthigh",
        name="P1 Power Prod Cnt High",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecsolar",
        name="P1 Power Solar",
        icon="mdi:solar-power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="elecsolarcnt",
        name="P1 Power Solar Cnt",
        icon="mdi:solar-power",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="heat",
        name="P1 Heat",
        icon="mdi:fire",
        native_unit_of_measurement="GJ",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="waterquantity",
        name="P1 waterquantity",
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="waterflow",
        name="P1 waterflow",
        icon="mdi:water-pump",
        native_unit_of_measurement="l/min",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=80): cv.positive_int,
        vol.Required(CONF_RESOURCES, default=list(SENSOR_LIST)): vol.All(
            cv.ensure_list, [vol.In(SENSOR_LIST)]
        ),
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup the Toon Smart Meter sensors."""

    session = async_get_clientsession(hass)
    data = ToonSmartMeterData(session, config.get(CONF_HOST), config.get(CONF_PORT))
    await data.async_update()

    entities = []
    for description in SENSOR_TYPES:
        if description.key in config[CONF_RESOURCES]:
            sensor = ToonSmartMeterSensor(description, data)
            entities.append(sensor)
    async_add_entities(entities, True)


class ToonSmartMeterData:
    """Handle Toon object and limit updates."""

    def __init__(self, session, host, port):
        """Initialize the data object."""
        self._session = session
        self._url = BASE_URL.format(host, port)
        self._data = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Download and update data from Toon."""
        try:
            async with async_timeout.timeout(5):
                response = await self._session.get(
                    self._url, headers={"Accept-Encoding": "identity"}
                )
                self._data = await response.json(content_type="text/javascript")
                _LOGGER.debug("Data received from Toon: %s", self._data)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.error("Cannot poll Toon using url: %s - %s", self._url, err)
            self._data = None
        except Exception as err:
            _LOGGER.error("Unknown error occurred while polling Toon: %s", err)
            self._data = None

    @property
    def latest_data(self):
        """Return the latest data object."""
        return self._data


def safe_get(_dict, keys, default=None):
    """Safe dictionary get with reduce."""
    def _reducer(d, key):
        if isinstance(d, dict):
            return d.get(key, default)
        return default
    return reduce(_reducer, keys, _dict)


class ToonSmartMeterSensor(SensorEntity):
    """Representation of a Smart Meter connected to Toon."""

    def __init__(self, description: SensorEntityDescription, data):
        """Initialize the sensor."""
        self.entity_description = description
        self._data = data
        self._state = None
        self._type = self.entity_description.key
        self._attr_icon = self.entity_description.icon
        self._attr_name = f"{SENSOR_PREFIX}{self.entity_description.name}"
        self._attr_state_class = self.entity_description.state_class
        self._attr_native_unit_of_measurement = self.entity_description.native_unit_of_measurement
        self._attr_device_class = self.entity_description.device_class
        self._attr_unique_id = f"{SENSOR_PREFIX}_{self._type}"
        self._discovery = False
        self._dev_id = {}

    def _validate_output(self, value):
        """Return 0 if the output from the Toon is NaN."""
        try:
            if str(value).lower() == "nan":
                return 0
        except (ValueError, TypeError):
            pass
        return value

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    async def async_update(self):
        """Get the latest data and use it to update our sensor state."""
        await self._data.async_update()
        energy = self._data.latest_data

        if not energy:
            return

        if not self._discovery:
            self._discover_devices(energy)
            self._discovery = True
            _LOGGER.debug("Discovered: '%s'", self._dev_id)

        self._update_state(energy)

    def _discover_devices(self, energy):
        """Discover available devices and map to sensor types."""
        for key in energy:
            dev = energy[key]
            
            # Gas
            if (dev["type"] in ["gas", "HAE_METER_v2_1", "HAE_METER_v3_1", "HAE_METER_v4_1"] and
                safe_get(energy, [key, "CurrentGasQuantity"], "NaN") != "NaN"):
                self._dev_id["gasused"] = key
                self._dev_id["gasusedcnt"] = key

            # Elec low tariff
            if (dev["type"] in ["elec_delivered_lt", "HAE_METER_v2_5", "HAE_METER_v3_6", 
                               "HAE_METER_v3_5", "HAE_METER_v4_6", "HAE_METER_HEAT_5"] and
                safe_get(energy, [key, "CurrentElectricityQuantity"], "NaN") != "NaN"):
                self._dev_id["elecusageflowlow"] = key
                self._dev_id["elecusagecntlow"] = key

            # Elec high tariff
            if (dev["type"] in ["elec_delivered_nt", "HAE_METER_v2_3", "HAE_METER_v3_3", 
                               "HAE_METER_v3_4", "HAE_METER_v4_4", "HAE_METER_HEAT_3"] and
                safe_get(energy, [key, "CurrentElectricityQuantity"], "NaN") != "NaN"):
                self._dev_id["elecusageflowhigh"] = key
                self._dev_id["elecusagecnthigh"] = key

            # Elec production low
            if (dev["type"] in ["elec_received_lt", "HAE_METER_v2_6", "HAE_METER_v3_7", "HAE_METER_v4_7"] and
                safe_get(energy, [key, "CurrentElectricityQuantity"], "NaN") != "NaN"):
                self._dev_id["elecprodflowlow"] = key
                self._dev_id["elecprodcntlow"] = key

            # Elec production high
            if (dev["type"] in ["elec_received_nt", "HAE_METER_v2_4", "HAE_METER_v3_5", "HAE_METER_v4_5"] and
                safe_get(energy, [key, "CurrentElectricityQuantity"], "NaN") != "NaN"):
                self._dev_id["elecprodflowhigh"] = key
                self._dev_id["elecprodcnthigh"] = key

            # Solar
            if (dev["type"] in ["HAE_METER_v3_3", "HAE_METER_v4_3"] and
                safe_get(energy, [key, "CurrentElectricityQuantity"], "NaN") != "NaN"):
                self._dev_id["elecsolar"] = key
                self._dev_id["elecsolarcnt"] = key

            # Heat
            if (dev["type"] in ["HAE_METER_v3_8", "HAE_METER_v4_8", "HAE_METER_HEAT_1"] and
                safe_get(energy, [key, "CurrentHeatQuantity"], "NaN") != "NaN"):
                self._dev_id["heat"] = key

            # Water
            if (dev["type"] in ["HAE_METER_v4_9"] and
                safe_get(energy, [key, "CurrentWaterQuantity"], "NaN") != "NaN"):
                self._dev_id["waterquantity"] = key
                self._dev_id["waterflow"] = key

    def _update_state(self, energy):
        """Update sensor state based on type."""
        state_map = {
            "gasused": lambda: float(energy[self._dev_id.get("gasused", "")]["CurrentGasFlow"]) / 1000 if "gasused" in self._dev_id else None,
            "gasusedcnt": lambda: float(energy[self._dev_id.get("gasusedcnt", "")]["CurrentGasQuantity"]) / 1000 if "gasusedcnt" in self._dev_id else None,
            "elecusageflowpulse": lambda: self._validate_output(self._get_pulse_flow(energy)),
            "elecusagecntpulse": lambda: self._validate_output(float(self._get_pulse_quantity(energy)) / 1000) if self._get_pulse_quantity(energy) else None,
            "elecusageflowlow": lambda: self._validate_output(energy[self._dev_id.get("elecusageflowlow", "")]["CurrentElectricityFlow"]) if "elecusageflowlow" in self._dev_id else None,
            "elecusagecntlow": lambda: self._validate_output(float(energy[self._dev_id.get("elecusagecntlow", "")]["CurrentElectricityQuantity"]) / 1000) if "elecusagecntlow" in self._dev_id else None,
            "elecusageflowhigh": lambda: self._validate_output(energy[self._dev_id.get("elecusageflowhigh", "")]["CurrentElectricityFlow"]) if "elecusageflowhigh" in self._dev_id else None,
            "elecusagecnthigh": lambda: self._validate_output(float(energy[self._dev_id.get("elecusagecnthigh", "")]["CurrentElectricityQuantity"]) / 1000) if "elecusagecnthigh" in self._dev_id else None,
            "elecprodflowlow": lambda: self._validate_output(energy[self._dev_id.get("elecprodflowlow", "")]["CurrentElectricityFlow"]) if "elecprodflowlow" in self._dev_id else None,
            "elecprodcntlow": lambda: self._validate_output(float(energy[self._dev_id.get("elecprodcntlow", "")]["CurrentElectricityQuantity"]) / 1000) if "elecprodcntlow" in self._dev_id else None,
            "elecprodflowhigh": lambda: self._validate_output(energy[self._dev_id.get("elecprodflowhigh", "")]["CurrentElectricityFlow"]) if "elecprodflowhigh" in self._dev_id else None,
            "elecprodcnthigh": lambda: self._validate_output(float(energy[self._dev_id.get("elecprodcnthigh", "")]["CurrentElectricityQuantity"]) / 1000) if "elecprodcnthigh" in self._dev_id else None,
            "elecsolar": lambda: self._validate_output(self._get_solar_flow(energy)),
            "elecsolarcnt": lambda: self._validate_output(float(self._get_solar_quantity(energy)) / 1000) if self._get_solar_quantity(energy) else None,
            "heat": lambda: self._validate_output(float(energy[self._dev_id.get("heat", "")]["CurrentHeatQuantity"]) / 1000) if "heat" in self._dev_id else None,
            "waterquantity": lambda: float(energy[self._dev_id.get("waterquantity", "")]["CurrentWaterQuantity"]) if "waterquantity" in self._dev_id else None,
            "waterflow": lambda: float(energy[self._dev_id.get("waterflow", "")]["CurrentWaterFlow"]) if "waterflow" in self._dev_id else None,
        }
        
        self._state = state_map.get(self._type, lambda: None)()
        _LOGGER.debug("Device: %s State: %s", self._type, self._state)

    def _get_pulse_flow(self, energy):
        """Get electricity flow from pulse devices."""
        for dev in ["dev_3.2", "dev_2.2", "dev_4.2", "dev_7.2"]:
            if dev in energy:
                return energy[dev]["CurrentElectricityFlow"]
        return None

    def _get_pulse_quantity(self, energy):
        """Get electricity quantity from pulse devices."""
        for dev in ["dev_3.2", "dev_2.2", "dev_4.2", "dev_7.2"]:
            if dev in energy:
                return energy[dev]["CurrentElectricityQuantity"]
        return None

    def _get_solar_flow(self, energy):
        """Get solar electricity flow."""
        for dev in ["dev_4.export", "dev_3.export", "dev_7.export", "dev_14.export"]:
            if dev in energy:
                return energy[dev]["CurrentElectricityFlow"]
        if self._type in self._dev_id:
            return energy[self._dev_id[self._type]]["CurrentElectricityFlow"]
        return None

    def _get_solar_quantity(self, energy):
        """Get solar electricity quantity."""
        for dev in ["dev_4.export", "dev_3.export", "dev_7.export", "dev_14.export"]:
            if dev in energy:
                return energy[dev]["CurrentElectricityQuantity"]
        if self._type in self._dev_id:
            return energy[self._dev_id[self._type]]["CurrentElectricityQuantity"]
        return None
