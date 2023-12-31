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
from homeassistant.const import UnitOfVolume, UnitOfEnergy, UnitOfPower, UnitOfTemperature
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_RESOURCES,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle, dt

BASE_URL = "http://{0}:{1}/hdrv_zwave?action=getDevices.json"
DEVICE_CLASS_WATER = "water"

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=10)

SENSOR_PREFIX = "Toon "
ATTR_MEASUREMENT = "measurement"
ATTR_SECTION = "section"
CONF_POWERPLUGS = "powerplugs"

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
        name="Power Use Cnt",
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
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="elecsolarcnt",
        name="P1 Power Solar Cnt",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="heat",
        name="P1 Heat",
        icon="mdi:fire",
        unit_of_measurement="Gj",
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
        unit_of_measurement = "l/m",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="powerplugflow",
        name="PowerPlug Power Use",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="powerplugcnt",
        name="PowerPlug Power Use Cnt",
        icon="mdi:flash",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),

)


PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=80): cv.positive_int,
        vol.Required(CONF_RESOURCES, default=list(SENSOR_LIST)): vol.All(
            cv.ensure_list, [vol.In(SENSOR_LIST)]
        ),
        vol.Optional(CONF_POWERPLUGS, default=list()): cv.ensure_list,
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup the Toon Smart Meter sensors."""

    session = async_get_clientsession(hass)
    data = ToonSmartMeterData(session, config.get(CONF_HOST), config.get(CONF_PORT))
    await data.async_update()

    # Create a new sensor for each sensor type.
    entities = []
    for description in SENSOR_TYPES:
        if description.key in config[CONF_RESOURCES]:
            entities.append(ToonSmartMeterSensor(description, data, ""))
        if description.key in ["powerplugflow", "powerplugcnt"]:
            for powerplug in config[CONF_POWERPLUGS]:
                entities.append(ToonSmartMeterSensor(description, data, powerplug))
    async_add_entities(entities, True)
    return True


# pylint: disable=abstract-method
class ToonSmartMeterData(object):
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
            with async_timeout.timeout(5):
                response = await self._session.get(
                    self._url, headers={"Accept-Encoding": "identity"}
                )
        except aiohttp.ClientError:
            _LOGGER.error("Cannot poll Toon using url: %s", self._url)
            return
        except asyncio.TimeoutError:
            _LOGGER.error(
                "Timeout error occurred while polling Toon using url: %s", self._url
            )
            return
        except Exception as err:
            _LOGGER.error("Unknown error occurred while polling Toon: %s", err)
            self._data = None
            return

        try:
            self._data = await response.json(content_type="text/javascript")
            _LOGGER.debug("Data received from Toon: %s", self._data)
        except Exception as err:
            _LOGGER.error("Cannot parse data received from Toon: %s", err)
            self._data = None

    @property
    def latest_data(self):
        """Return the latest data object."""
        if self._data:
            return self._data
        return None


class ToonSmartMeterSensor(SensorEntity):
    """Representation of a Smart Meter connected to Toon."""

    def __init__(self, description: SensorEntityDescription, data, powerplug):
        """Initialize the sensor."""
        self._entity_description = description
        self._data = data

        self.device_type = self._entity_description.key
        self.powerplug_name = powerplug

        if self._entity_description.key in ["powerplugflow", "powerplugcnt"]:
            self._attr_name = f"{SENSOR_PREFIX} {self._entity_description.name} {self.powerplug_name}"
            self._attr_unique_id = f"{SENSOR_PREFIX}_{self._entity_description.name}_{self.powerplug_name}"
        else:
            self._attr_name = f"{SENSOR_PREFIX} {self._entity_description.name}"
            self._attr_unique_id = f"{SENSOR_PREFIX}_{self._entity_description.name}"

        self._attr_icon = self._entity_description.icon
        self._attr_state_class = self._entity_description.state_class
        self._attr_native_unit_of_measurement = self._entity_description.native_unit_of_measurement
        self._attr_device_class = self._entity_description.device_class
        self._state = None
        self._discovery = False
        self._dev_id = {}

    def _validateOutput(self, value):
        """Return 0 if the output from the Toon is NaN (happens after a reboot)"""
        try:
            if value.lower() == "nan":
                value = 0
        except:
            return value

        return value

    @property
    def state(self):
        """Return the state of the sensor. (total/current power consumption/production or total gas used)"""
        return self._state

    async def async_update(self):
        """Get the latest data and use it to update our sensor state."""

        await self._data.async_update()
        energy = self._data.latest_data

        if not energy:
            return

        if self._discovery == False:
            for key in energy:
                dev = energy[key]

                """elec verbruik pulse"""
                if (
                    key in ["dev_2.2", "dev_3.2", "dev_4.2", "dev_7.2", "dev_9.2"]
                    and safe_get(
                        energy, [key, "CurrentElectricityQuantity"], default="NaN"
                    )
                    != "NaN"
                ):
                    self._dev_id["elecusageflowpulse"] = key
                    self._dev_id["elecusagecntpulse"] = key

                """gas verbruik"""
                if (
                    dev["type"] in ["gas", "HAE_METER_v2_1", "HAE_METER_v3_1", "HAE_METER_v4_1"]
                    and safe_get(energy, [key, "CurrentGasQuantity"], default="NaN")
                    != "NaN"
                ):
                    self._dev_id["gasused"] = key
                    self._dev_id["gasusedcnt"] = key

                """elec verbruik laag"""
                if (
                    dev["type"]
                    in [
                        "elec_delivered_lt",
                        "HAE_METER_v2_5",
                        "HAE_METER_v3_6",
                        "HAE_METER_v3_5",
                        "HAE_METER_v4_6",
                        "HAE_METER_HEAT_5",
                    ]
                    and safe_get(
                        energy, [key, "CurrentElectricityQuantity"], default="NaN"
                    )
                    != "NaN"
                ):
                    self._dev_id["elecusageflowlow"] = key
                    self._dev_id["elecusagecntlow"] = key

                """elec verbruik hoog/normaal"""
                if (
                    dev["type"]
                    in [
                        "elec_delivered_nt",
                        "HAE_METER_v2_3",
                        "HAE_METER_v3_3",
                        "HAE_METER_v3_4",
                        "HAE_METER_v4_4",
                        "HAE_METER_HEAT_3",
                    ]
                    and safe_get(
                        energy, [key, "CurrentElectricityQuantity"], default="NaN"
                    )
                    != "NaN"
                ):
                    self._dev_id["elecusageflowhigh"] = key
                    self._dev_id["elecusagecnthigh"] = key

                """elec teruglevering laag"""
                if (
                    dev["type"]
                    in [
                        "elec_received_lt",
                        "HAE_METER_v2_6",
                        "HAE_METER_v3_7",
                        "HAE_METER_v4_7",
                        "HAE_METER_HEAT_6",
                    ]
                    and safe_get(
                        energy, [key, "CurrentElectricityQuantity"], default="NaN"
                    )
                    != "NaN"
                ):
                    self._dev_id["elecprodflowlow"] = key
                    self._dev_id["elecprodcntlow"] = key

                """elec teruglevering hoog/normaal"""
                if (
                    dev["type"]
                    in [
                        "elec_received_nt",
                        "HAE_METER_v2_4",
                        "HAE_METER_v3_5",
                        "HAE_METER_v4_5",
                        "HAE_METER_HEAT_4",
                    ]
                    and safe_get(
                        energy, [key, "CurrentElectricityQuantity"], default="NaN"
                    )
                    != "NaN"
                ):
                    self._dev_id["elecprodflowhigh"] = key
                    self._dev_id["elecprodcnthigh"] = key

                """solar"""
                if (
                    dev["type"]
                    in [
                        "HAE_METER_v3_3",
                        "HAE_METER_v4_3",
                    ]
                    and safe_get(
                        energy, [key, "CurrentElectricityQuantity"], default="NaN"
                    )
                    != "NaN"
                ):
                    self._dev_id["elecsolar"] = key
                    self._dev_id["elecsolarcnt"] = key

                """heat"""
                if (
                    dev["type"]
                    in [
                        "HAE_METER_v3_8",
                        "HAE_METER_v4_8",
                        "HAE_METER_HEAT_1",
                    ]
                    and safe_get(
                        energy, [key, "CurrentHeatQuantity"], default="NaN"
                    )
                    != "NaN"
                ):
                    self._dev_id["heat"] = key

                """water"""
                if (
                    dev["type"]
                    in [
                        "HAE_METER_v4_9",
                    ]
                    and safe_get(
                        energy, [key, "CurrentWaterQuantity"], default="NaN"
                    )
                    != "NaN"
                ):
                    self._dev_id["waterquantity"] = key
                    self._dev_id["waterflow"] = key

            self._discovery = True
            _LOGGER.debug("Discovered: '%s'", self._dev_id)

            """gas verbruik laatste uur"""
        if self.device_type == "gasused":
            if self.device_type in self._dev_id:
                self._state = (
                    float(energy[self._dev_id[self.device_type]]["CurrentGasFlow"]) / 1000
                )

            """gas verbruik teller laatste uur"""
        elif self.device_type == "gasusedcnt":
            if self.device_type in self._dev_id:
                self._state = (
                    float(energy[self._dev_id[self.device_type]]["CurrentGasQuantity"]) / 1000
                )

            """elec verbruik puls"""
        elif self.device_type == "elecusageflowpulse":
            if self.device_type in self._dev_id:
                self._state = (
                    float(energy[self._dev_id[self.device_type]]["CurrentElectricityFlow"])
                )

            """elec verbruik teller puls"""
        elif self.device_type == "elecusagecntpulse":
            if self.device_type in self._dev_id:
                self._state = (
                    float(energy[self._dev_id[self.device_type]]["CurrentElectricityQuantity"]) / 1000
                )

            """elec verbruik laag"""
        elif self.device_type == "elecusageflowlow":
            if self.device_type in self._dev_id:
                self._state = self._validateOutput(
                    energy[self._dev_id[self.device_type]]["CurrentElectricityFlow"]
                )

            """elec verbruik teller laag"""
        elif self.device_type == "elecusagecntlow":
            if self.device_type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self.device_type]]["CurrentElectricityQuantity"]
                    )
                    / 1000
                )

            """elec verbruik hoog/normaal"""
        elif self.device_type == "elecusageflowhigh":
            if self.device_type in self._dev_id:
                self._state = self._validateOutput(
                    energy[self._dev_id[self.device_type]]["CurrentElectricityFlow"]
                )

            """elec verbruik teller hoog/normaal"""
        elif self.device_type == "elecusagecnthigh":
            if self.device_type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self.device_type]]["CurrentElectricityQuantity"]
                    )
                    / 1000
                )

            """elec teruglever laag"""
        elif self.device_type == "elecprodflowlow":
            if self.device_type in self._dev_id:
                self._state = self._validateOutput(
                    energy[self._dev_id[self.device_type]]["CurrentElectricityFlow"]
                )

            """elec teruglever teller laag"""
        elif self.device_type == "elecprodcntlow":
            if self.device_type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self.device_type]]["CurrentElectricityQuantity"]
                    )
                    / 1000
                )

            """elec teruglever hoog/normaal"""
        elif self.device_type == "elecprodflowhigh":
            if self.device_type in self._dev_id:
                self._state = self._validateOutput(
                    energy[self._dev_id[self.device_type]]["CurrentElectricityFlow"]
                )

            """elec teruglever teller hoog/normaal"""
        elif self.device_type == "elecprodcnthigh":
            if self.device_type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self.device_type]]["CurrentElectricityQuantity"]
                    )
                    / 1000
                )

            """zon op toon"""
        elif self.device_type == "elecsolar":
            if "dev_4.export" in energy:
                self._state = self._validateOutput(
                    energy["dev_4.export"]["CurrentElectricityFlow"]
                )
            elif "dev_3.export" in energy:
                self._state = self._validateOutput(
                    energy["dev_3.export"]["CurrentElectricityFlow"]
                )
            elif "dev_7.export" in energy:
                self._state = self._validateOutput(
                    energy["dev_7.export"]["CurrentElectricityFlow"]
                )  
            elif self.device_type in self._dev_id:
                self._state = self._validateOutput(
                    energy[self._dev_id[self.device_type]]["CurrentElectricityFlow"]
                )

            """zon op toon teller"""
        elif self.device_type == "elecsolarcnt":
            if "dev_4.export" in energy:
                self._state = self._validateOutput(
                    float(energy["dev_4.export"]["CurrentElectricityQuantity"]) / 1000
                )
            elif "dev_3.export" in energy:
                self._state = self._validateOutput(
                    float(energy["dev_3.export"]["CurrentElectricityQuantity"]) / 1000
                )
            elif "dev_7.export" in energy:
                self._state = self._validateOutput(
                    float(energy["dev_7.export"]["CurrentElectricityQuantity"]) / 1000
                )             
            elif self.device_type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self.device_type]]["CurrentElectricityQuantity"]
                    )
                    / 1000
                )

        elif self.device_type == "heat":
            if self.device_type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self.device_type]]["CurrentHeatQuantity"]
                    )
                    / 1000
                )

        elif self.device_type == "waterquantity":
            if self.device_type in self._dev_id:
                self._state = (
                    float(energy[self._dev_id[self.device_type]]["CurrentWaterQuantity"])
                )

        elif self.device_type == "waterflow":
            if self.device_type in self._dev_id:
                self._state = (
                    float(energy[self._dev_id[self.device_type]]["CurrentWaterFlow"])
                )

        elif self.device_type == "powerplugflow":
            for key in energy:
                dev = energy[key]
                if dev["name"] == self.powerplug_name:
                    self._state = self._validateOutput(
                        float(
                            dev["CurrentElectricityFlow"]
                        )
                    )
    
        elif self.device_type == "powerplugcnt":
            for key in energy:
                dev = energy[key]
                if dev["name"] == self.powerplug_name:
                    self._state = self._validateOutput(
                        float(
                            dev["CurrentElectricityQuantity"]
                        )
                        / 1000
                    )

        _LOGGER.debug(f"Device: {self.device_type} State: {self._state} PowerPlug: {self.powerplug_name}")


def safe_get(_dict, keys, default=None):
    def _reducer(d, key):
        if isinstance(d, dict):
            return d.get(key, default)
        return default

    return reduce(_reducer, keys, _dict)
