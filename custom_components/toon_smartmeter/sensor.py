"""
Support for reading Smart Meter data using Toon thermostats meteradapter.
Only works for rooted Toon.

configuration.yaml

sensor:
    - platform: toon_smartmeter
        host: IP_ADDRESS
        port: 80
        scan_interval: 10
        resources:
            - gasused
            - gasusedcnt
            - elecusageflowpulse
            - elecusagecntpulse
            - elecusageflowlow
            - elecusagecntlow
            - elecusageflowhigh
            - elecusagecnthigh
            - elecprodflowlow
            - elecprodcntlow
            - elecprodflowhigh
            - elecprodcnthigh
            - elecsolar
            - elecsolarcnt
            - heat
"""
import logging
from datetime import timedelta
import aiohttp
import asyncio
import async_timeout
import voluptuous as vol
from functools import reduce

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, CONF_RESOURCES
    )
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle

BASE_URL = 'http://{0}:{1}/hdrv_zwave?action=getDevices.json'
_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=10)

SENSOR_PREFIX = 'Toon '
SENSOR_TYPES = {
    'gasused': ['Gas Used Last Hour', 'm3', 'mdi:fire'],
    'gasusedcnt': ['Gas Used Cnt', 'm3', 'mdi:fire'],
    'elecusageflowpulse': ['Power Use', 'Watt', 'mdi:flash'],
    'elecusageflowlow': ['P1 Power Use Low', 'Watt', 'mdi:flash'],
    'elecusageflowhigh': ['P1 Power Use High', 'Watt', 'mdi:flash'],
    'elecprodflowlow': ['P1 Power Prod Low', 'Watt', 'mdi:flash'],
    'elecprodflowhigh': ['P1 Power Prod High', 'Watt', 'mdi:flash'],
    'elecusagecntpulse': ['Power Use Cnt', 'kWh', 'mdi:flash'],
    'elecusagecntlow': ['P1 Power Use Cnt Low', 'kWh', 'mdi:flash'],
    'elecusagecnthigh': ['P1 Power Use Cnt High', 'kWh', 'mdi:flash'],
    'elecprodcntlow': ['P1 Power Prod Cnt Low', 'kWh', 'mdi:flash'],
    'elecprodcnthigh': ['P1 Power Prod Cnt High', 'kWh', 'mdi:flash'],
    'elecsolar': ['P1 Power Solar', 'Watt', 'mdi:weather-sunny'],
    'elecsolarcnt': ['P1 Power Solar Cnt', 'kWh', 'mdi:weather-sunny'],
    'heat': ['P1 Heat', '', 'mdi:fire'],
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_PORT, default=80): cv.positive_int,
    vol.Required(CONF_RESOURCES, default=list(SENSOR_TYPES)):
        vol.All(cv.ensure_list, [vol.In(SENSOR_TYPES)]),
})

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Setup the Toon Smart Meter sensors."""

    session = async_get_clientsession(hass)
    data = ToonSmartMeterData(session, config.get(CONF_HOST), config.get(CONF_PORT))
    await data.async_update()

    entities = []
    for resource in config[CONF_RESOURCES]:
        sensor_type = resource.lower()
        name = SENSOR_PREFIX + SENSOR_TYPES[resource][0]
        unit = SENSOR_TYPES[resource][1]
        icon = SENSOR_TYPES[resource][2]

        _LOGGER.debug("Adding Toon Smart Meter sensor: {}, {}, {}, {}".format(name, sensor_type, unit, icon))
        entities.append(ToonSmartMeterSensor(data, name, sensor_type, unit, icon))

    async_add_entities(entities, True)

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
                response = await self._session.get(self._url, headers={"Accept-Encoding": "identity"})
        except aiohttp.ClientError:
            _LOGGER.error("Cannot poll Toon using url: %s", self._url)
            return
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout error occurred while polling Toon using url: %s", self._url)
            return
        except Exception as err:
            _LOGGER.error("Unknown error occurred while polling Toon: %s", err)
            self._data = None
            return

        try:
            self._data = await response.json(content_type='text/javascript')
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

class ToonSmartMeterSensor(Entity):
    """Representation of a Smart Meter connected to Toon."""

    def __init__(self, data, name, sensor_type, unit, icon):
        """Initialize the sensor."""
        self._data = data
        self._name = name
        self._type = sensor_type
        self._unit = unit
        self._icon = icon

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
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return self._icon

    @property
    def state(self):
        """Return the state of the sensor. (total/current power consumption/production or total gas used)"""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit

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
                if dev['type'] in ['gas', 'HAE_METER_v2_1', 'HAE_METER_v3_1'] and safe_get(energy, [key,'CurrentGasQuantity'], default='NaN') != 'NaN':
                    self._dev_id['gasused'] = key
                    self._dev_id['gasusedcnt'] = key

                """elec verbruik laag"""
                if dev['type'] in ['elec_delivered_lt', 'HAE_METER_v2_5', 'HAE_METER_v3_6', 'HAE_METER_v3_5'] and safe_get(energy, [key,'CurrentElectricityQuantity'], default='NaN') != 'NaN':
                    self._dev_id['elecusageflowlow'] = key
                    self._dev_id['elecusagecntlow'] = key

                """elec verbruik hoog/normaal"""
                if dev['type'] in ['elec_delivered_nt', 'HAE_METER_v2_3', 'HAE_METER_v3_3', 'HAE_METER_v3_4'] and safe_get(energy, [key,'CurrentElectricityQuantity'], default='NaN') != 'NaN':
                    self._dev_id['elecusageflowhigh'] = key
                    self._dev_id['elecusagecnthigh'] = key

                """elec teruglevering laag"""
                if dev['type'] in ['elec_received_lt', 'HAE_METER_v2_6', 'HAE_METER_v3_7'] and safe_get(energy, [key,'CurrentElectricityQuantity'], default='NaN') != 'NaN':
                    self._dev_id['elecprodflowlow'] = key
                    self._dev_id['elecprodcntlow'] = key

                """elec teruglevering hoog/normaal"""
                if dev['type'] in ['elec_received_nt', 'HAE_METER_v2_4', 'HAE_METER_v3_5'] and safe_get(energy, [key,'CurrentElectricityQuantity'], default='NaN') != 'NaN':
                    self._dev_id['elecprodflowhigh'] = key
                    self._dev_id['elecprodcnthigh'] = key

            self._discovery = True
            _LOGGER.debug("Discovered: '%s'", self._dev_id)

            """gas verbruik laatste uur"""
        if self._type == 'gasused':
            if self._type in self._dev_id:
                self._state = float(energy[self._dev_id[self._type]]["CurrentGasFlow"])/1000

            """gas verbruik teller laatste uur"""
        elif self._type == 'gasusedcnt':
            if self._type in self._dev_id:
                self._state = float(energy[self._dev_id[self._type]]["CurrentGasQuantity"])/1000

            """elec verbruik puls"""
        elif self._type == 'elecusageflowpulse':
            if 'dev_3.2' in energy:
                self._state = self._validateOutput(energy["dev_3.2"]["CurrentElectricityFlow"])
            elif 'dev_2.2' in energy:
                self._state = self._validateOutput(energy["dev_2.2"]["CurrentElectricityFlow"])
            elif 'dev_4.2' in energy:
                self._state = self._validateOutput(energy["dev_4.2"]["CurrentElectricityFlow"])
            elif 'dev_7.2' in energy:
                self._state = self._validateOutput(energy["dev_7.2"]["CurrentElectricityFlow"])

            """elec verbruik teller puls"""
        elif self._type == 'elecusagecntpulse':
            if 'dev_3.2' in energy:
                self._state = self._validateOutput(float(energy["dev_3.2"]["CurrentElectricityQuantity"])/1000)
            elif 'dev_2.2' in energy:
                self._state = self._validateOutput(float(energy["dev_2.2"]["CurrentElectricityQuantity"])/1000)
            elif 'dev_4.2' in energy:
                self._state = self._validateOutput(float(energy["dev_4.2"]["CurrentElectricityQuantity"])/1000)
            elif 'dev_7.2' in energy:
                self._state = self._validateOutput(float(energy["dev_7.2"]["CurrentElectricityQuantity"])/1000)

            """elec verbruik laag"""
        elif self._type == 'elecusageflowlow':
            if self._type in self._dev_id:
                self._state = self._validateOutput(energy[self._dev_id[self._type]]["CurrentElectricityFlow"])

            """elec verbruik teller laag"""
        elif self._type == 'elecusagecntlow':
            if self._type in self._dev_id:
                self._state = self._validateOutput(float(energy[self._dev_id[self._type]]["CurrentElectricityQuantity"])/1000)

            """elec verbruik hoog/normaal"""
        elif self._type == 'elecusageflowhigh':
            if self._type in self._dev_id:
                self._state = self._validateOutput(energy[self._dev_id[self._type]]["CurrentElectricityFlow"])

            """elec verbruik teller hoog/normaal"""
        elif self._type == 'elecusagecnthigh':
            if self._type in self._dev_id:
                self._state = self._validateOutput(float(energy[self._dev_id[self._type]]["CurrentElectricityQuantity"])/1000)

            """elec teruglever laag"""
        elif self._type == 'elecprodflowlow':
            if self._type in self._dev_id:
                self._state = self._validateOutput(energy[self._dev_id[self._type]]["CurrentElectricityFlow"])

            """elec teruglever teller laag"""
        elif self._type == 'elecprodcntlow':
            if self._type in self._dev_id:
                self._state = self._validateOutput(float(energy[self._dev_id[self._type]]["CurrentElectricityQuantity"])/1000)

            """elec teruglever hoog/normaal"""
        elif self._type == 'elecprodflowhigh':
            if self._type in self._dev_id:
                self._state = self._validateOutput(energy[self._dev_id[self._type]]["CurrentElectricityFlow"])

            """elec teruglever teller hoog/normaal"""
        elif self._type == 'elecprodcnthigh':
            if self._type in self._dev_id:
                self._state = self._validateOutput(float(energy[self._dev_id[self._type]]["CurrentElectricityQuantity"])/1000)

            """zon op toon"""
        elif self._type == 'elecsolar':
            if 'dev_3.export' in energy:
                self._state = self._validateOutput(energy["dev_3.export"]["CurrentElectricityFlow"])
            elif 'dev_2.3' in energy:
                self._state = self._validateOutput(energy["dev_2.3"]["CurrentElectricityFlow"])
            elif 'dev_3.3' in energy:
                self._state = self._validateOutput(energy["dev_3.3"]["CurrentElectricityFlow"])
            elif 'dev_4.3' in energy:
                self._state = self._validateOutput(energy["dev_4.3"]["CurrentElectricityFlow"])

            """zon op toon teller"""
        elif self._type == 'elecsolarcnt':
            if 'dev_3.export' in energy:
                self._state = self._validateOutput(float(energy["dev_3.export"]["CurrentElectricityQuantity"])/1000)
            elif 'dev_2.3' in energy:
                self._state = self._validateOutput(float(energy["dev_2.3"]["CurrentElectricityQuantity"])/1000)
            elif 'dev_3.3' in energy:
                self._state = self._validateOutput(float(energy["dev_3.3"]["CurrentElectricityQuantity"])/1000)
            elif 'dev_4.3' in energy:
                self._state = self._validateOutput(float(energy["dev_4.3"]["CurrentElectricityQuantity"])/1000)

        elif self._type == 'heat':
            if 'dev_2.8' in energy:
                self._state = self._validateOutput(float(energy["dev_2.8"]["CurrentHeatQuantity"])/1000)
            elif 'dev_4.8' in energy:
                self._state = self._validateOutput(float(energy["dev_4.8"]["CurrentHeatQuantity"])/1000)

        _LOGGER.debug("Device: {} State: {}".format(self._type, self._state))

def safe_get(_dict, keys, default=None):

    def _reducer(d, key):
        if isinstance(d, dict):
            return d.get(key, default)
        return default

    return reduce(_reducer, keys, _dict)
