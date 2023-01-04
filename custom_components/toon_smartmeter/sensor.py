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
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
    VOLUME_CUBIC_METERS,
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
        native_unit_of_measurement=VOLUME_CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="gasusedcnt",
        name="Gas Used Cnt",
        icon="mdi:gas-cylinder",
        native_unit_of_measurement=VOLUME_CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecusageflowpulse",
        name="Power Use",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
    ),
    SensorEntityDescription(
        key="elecusageflowlow",
        name="P1 Power Use Low",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="elecusageflowhigh",
        name="P1 Power Use High",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="elecprodflowlow",
        name="P1 Power Prod Low",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="elecprodflowhigh",
        name="P1 Power Prod High",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="elecusagecntpulse",
        name="P1 Power Use Cnt",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecusagecntlow",
        name="P1 Power Use Cnt Low",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecusagecnthigh",
        name="P1 Power Use Cnt High",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecprodcntlow",
        name="P1 Power Prod Cnt Low",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecprodcnthigh",
        name="P1 Power Prod Cnt High",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="elecsolar",
        name="P1 Power Solar",
        icon="mdi:flash",
        native_unit_of_measurement=POWER_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="elecsolarcnt",
        name="P1 Power Solar Cnt",
        icon="mdi:flash",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
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
        native_unit_of_measurement=VOLUME_CUBIC_METERS,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="waterflow",
        name="P1 waterflow",
        icon="mdi:water-pump",
        unit_of_measurement = "l/m",
        device_class=SensorDeviceClass.ENERGY,
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

    # Create a new sensor for each sensor type.
    entities = []
    for description in SENSOR_TYPES:
        if description.key in config[CONF_RESOURCES]:
            sensor = ToonSmartMeterSensor(description, data)
            entities.append(sensor)
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

    def __init__(self, description: SensorEntityDescription, data):
        """Initialize the sensor."""
        self.entity_description = description
        self._data = data

        self._state = None

        self._type = self.entity_description.key
        self._attr_icon = self.entity_description.icon
        self._attr_name = SENSOR_PREFIX + self.entity_description.name
        self._attr_state_class = self.entity_description.state_class
        self._attr_native_unit_of_measurement = self.entity_description.native_unit_of_measurement
        self._attr_device_class = self.entity_description.device_class
        self._attr_unique_id = f"{SENSOR_PREFIX}_{self._type}"

        self._discovery = False
        self._dev_id = {}

    def _validateOutput(self, value):
        """Return 0 if the output from the Toon is NaN (happens after a reboot)"""
        try:
            if value.lower() == "nan":
                value = 0    @property
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
        if self._type == "gasused":
            if self._type in self._dev_id:
                self._state = (
                    float(energy[self._dev_id[self._type]]["CurrentGasFlow"]) / 1000
                )

            """gas verbruik teller laatste uur"""
        elif self._type == "gasusedcnt":
            if self._type in self._dev_id:
                self._state = (
                    float(energy[self._dev_id[self._type]]["CurrentGasQuantity"]) / 1000
                )

            """elec verbruik puls"""
        elif self._type == "elecusageflowpulse":
            if "dev_3.2" in energy:
                self._state = self._validateOutput(
                    energy["dev_3.2"]["CurrentElectricityFlow"]
                )
            elif "dev_2.2" in energy:
                self._state = self._validateOutput(
                    energy["dev_2.2"]["CurrentElectricityFlow"]
                )
            elif "dev_4.2" in energy:
                self._state = self._validateOutput(
                    energy["dev_4.2"]["CurrentElectricityFlow"]
                )
            elif "dev_7.2" in energy:
                self._state = self._validateOutput(
                    energy["dev_7.2"]["CurrentElectricityFlow"]
                )

            """elec verbruik teller puls"""
        elif self._type == "elecusagecntpulse":
            if "dev_3.2" in energy:
                self._state = self._validateOutput(
                    float(energy["dev_3.2"]["CurrentElectricityQuantity"]) / 1000
                )
            elif "dev_2.2" in energy:
                self._state = self._validateOutput(
                    float(energy["dev_2.2"]["CurrentElectricityQuantity"]) / 1000
                )
            elif "dev_4.2" in energy:
                self._state = self._validateOutput(
                    float(energy["dev_4.2"]["CurrentElectricityQuantity"]) / 1000
                )
            elif "dev_7.2" in energy:
                self._state = self._validateOutput(
                    float(energy["dev_7.2"]["CurrentElectricityQuantity"]) / 1000
                )

            """elec verbruik laag"""
        elif self._type == "elecusageflowlow":
            if self._type in self._dev_id:
                self._state = self._validateOutput(
                    energy[self._dev_id[self._type]]["CurrentElectricityFlow"]
                )

            """elec verbruik teller laag"""
        elif self._type == "elecusagecntlow":
            if self._type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self._type]]["CurrentElectricityQuantity"]
                    )
                    / 1000
                )

            """elec verbruik hoog/normaal"""
        elif self._type == "elecusageflowhigh":
            if self._type in self._dev_id:
                self._state = self._validateOutput(
                    energy[self._dev_id[self._type]]["CurrentElectricityFlow"]
                )

            """elec verbruik teller hoog/normaal"""
        elif self._type == "elecusagecnthigh":
            if self._type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self._type]]["CurrentElectricityQuantity"]
                    )
                    / 1000
                )

            """elec teruglever laag"""
        elif self._type == "elecprodflowlow":
            if self._type in self._dev_id:
                self._state = self._validateOutput(
                    energy[self._dev_id[self._type]]["CurrentElectricityFlow"]
                )

            """elec teruglever teller laag"""
        elif self._type == "elecprodcntlow":
            if self._type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self._type]]["CurrentElectricityQuantity"]
                    )
                    / 1000
                )

            """elec teruglever hoog/normaal"""
        elif self._type == "elecprodflowhigh":
            if self._type in self._dev_id:
                self._state = self._validateOutput(
                    energy[self._dev_id[self._type]]["CurrentElectricityFlow"]
                )

            """elec teruglever teller hoog/normaal"""
        elif self._type == "elecprodcnthigh":
            if self._type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self._type]]["CurrentElectricityQuantity"]
                    )
                    / 1000
                )

            """zon op toon"""
        elif self._type == "elecsolar":
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
            elif self._type in self._dev_id:
                self._state = self._validateOutput(
                    energy[self._dev_id[self._type]]["CurrentElectricityFlow"]
                )
            """zon op toon teller"""
        elif self._type == "elecsolarcnt":
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
            elif self._type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self._type]]["CurrentElectricityQuantity"]
                    )
                    / 1000
                )

        elif self._type == "heat":
            if self._type in self._dev_id:
                self._state = self._validateOutput(
                    float(
                        energy[self._dev_id[self._type]]["CurrentHeatQuantity"]
                    )
                    / 1000
                )

        elif self._type == "waterquantity":
            if self._type in self._dev_id:
                self._state = (
                    float(energy[self._dev_id[self._type]]["CurrentWaterQuantity"])
                )

        elif self._type == "waterflow":
            if self._type in self._dev_id:
                self._state = (
                    float(energy[self._dev_id[self._type]]["CurrentWaterFlow"])
                )


        _LOGGER.debug("Device: {} State: {}".format(self._type, self._state))


def safe_get(_dict, keys, default=None):
    def _reducer(d, key):
        if isinstance(d, dict):
            return d.get(key, default)
        return default

    return reduce(_reducer, keys, _dict)
