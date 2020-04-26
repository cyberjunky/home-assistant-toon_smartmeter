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

    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)

    toondata = ToonSmartMeterData(hass, host, port)
    await toondata.async_update()

    entities = []
    for resource in config[CONF_RESOURCES]:
        sensor_type = resource.lower()
        name = SENSOR_PREFIX + SENSOR_TYPES[resource][0]
        unit = SENSOR_TYPES[resource][1]
        icon = SENSOR_TYPES[resource][2]

        _LOGGER.debug("Adding Toon Smart Meter sensor: {}, {}, {}, {}".format(name, sensor_type, unit, icon))
        entities.append(ToonSmartMeterSensor(toondata, name, sensor_type, unit, icon))

    async_add_entities(entities, True)

# pylint: disable=abstract-method
class ToonSmartMeterData(object):
    """Handle Toon object and limit updates."""

    def __init__(self, hass, host, port):
        """Initialize the data object."""

        self._hass = hass
        self._host = host
        self._port = port

        self._url = BASE_URL.format(self._host, self._port)
        self._data = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Download and update data from Toon."""
        try:
            websession = async_get_clientsession(self._hass)
            with async_timeout.timeout(5):
                response = await websession.get(self._url)
            _LOGGER.debug(
                "Response status from Toon: %s", response.status
            ) 
        except (asyncio.TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.error("Cannot connect to Toon: %s", err)
            self._data = None
            return
        except Exception as err:
            _LOGGER.error("Error downloading from Toon: %s", err)
            self._data = None
            return

        try:
            self._data = await response.json(content_type='text/javascript')
            _LOGGER.debug("Data received from Toon: %s", self._data)
        except Exception as err:
            _LOGGER.error("Cannot parse data from Toon: %s", err)
            self._data = None
            return

    @property
    def latest_data(self):
        """Return the latest data object."""
        if self._data:
            return self._data
        return None

class ToonSmartMeterSensor(Entity):
    """Representation of a Smart Meter connected to Toon."""

    def __init__(self, toondata, name, sensor_type, unit, icon):
        """Initialize the sensor."""
        self._toondata = toondata
        self._name = name
        self._type = sensor_type
        self._unit = unit
        self._icon = icon

        self._state = None
        self._discovery = False
        self._dev_id = {}

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

        await self._toondata.async_update()
        energy = self._toondata.latest_data

        if energy:
            if self._discovery == False:
                
                _LOGGER.debug("Doing discovery")

                for key in energy:
                    dev = energy[key]

                    if dev['type'] in ['gas', 'HAE_METER_v2_1', 'HAE_METER_v3_1']:
                        self._dev_id['gasused'] = key
                        self._dev_id['gasusedcnt'] = key

                    if dev['type'] in ['elec_delivered_lt', 'HAE_METER_v2_5', 'HAE_METER_v3_6', 'HAE_METER_v3_5']:
                        self._dev_id['elecusageflowlow'] = key
                        self._dev_id['elecusagecntlow'] = key

                    if dev['type'] in ['elec_delivered_nt', 'HAE_METER_v2_3', 'HAE_METER_v3_4']:
                        self._dev_id['elecusageflowhigh'] = key
                        self._dev_id['elecusagecnthigh'] = key

                    if dev['type'] in ['elec_received_lt', 'HAE_METER_v2_6', 'HAE_METER_v3_7']:
                        self._dev_id['elecprodflowlow'] = key
                        self._dev_id['elecprodcntlow'] = key

                    if dev['type'] in ['elec_received_nt', 'HAE_METER_v2_4', 'HAE_METER_v3_5']:
                        self._dev_id['elecprodflowhigh'] = key
                        self._dev_id['elecprodcnthigh'] = key

                self._discovery = True

            if self._type == 'gasused':
                if self._type in self._dev_id:
                    self._state = float(energy[self._dev_id[self._type]]["CurrentGasFlow"])/1000

            elif self._type == 'gasusedcnt':
                if self._type in self._dev_id:
                    self._state = float(energy[self._dev_id[self._type]]["CurrentGasQuantity"])/1000

            elif self._type == 'elecusageflowpulse':
                if 'dev_3.2' in energy:
                    self._state = energy["dev_3.2"]["CurrentElectricityFlow"]
                elif 'dev_2.2' in energy:
                    self._state = energy["dev_2.2"]["CurrentElectricityFlow"]
                elif 'dev_4.2' in energy:
                    self._state = energy["dev_4.2"]["CurrentElectricityFlow"]

            elif self._type == 'elecusagecntpulse':
                if 'dev_3.2' in energy:
                    self._state = float(energy["dev_3.2"]["CurrentElectricityQuantity"])/1000
                elif 'dev_2.2' in energy:
                    self._state = float(energy["dev_2.2"]["CurrentElectricityQuantity"])/1000
                elif 'dev_4.2' in energy:
                    self._state = float(energy["dev_4.2"]["CurrentElectricityQuantity"])/1000

            elif self._type == 'elecusageflowlow':
                if self._type in self._dev_id:
                    self._state = energy[self._dev_id[self._type]]["CurrentElectricityFlow"]

            elif self._type == 'elecusagecntlow':
                if self._type in self._dev_id:
                    self._state = float(energy[self._dev_id[self._type]]["CurrentElectricityQuantity"])/1000

            elif self._type == 'elecusageflowhigh':
                if self._type in self._dev_id:
                    self._state = energy[self._dev_id[self._type]]["CurrentElectricityFlow"]

            elif self._type == 'elecusagecnthigh':
                if self._type in self._dev_id:
                    self._state = float(energy[self._dev_id[self._type]]["CurrentElectricityQuantity"])/1000

            elif self._type == 'elecprodflowlow':
                if self._type in self._dev_id:
                    self._state = energy[self._dev_id[self._type]]["CurrentElectricityFlow"]

            elif self._type == 'elecprodcntlow':
                if self._type in self._dev_id:
                    self._state = float(energy[self._dev_id[self._type]]["CurrentElectricityQuantity"])/1000

            elif self._type == 'elecprodflowhigh':
                if self._type in self._dev_id:
                    self._state = energy[self._dev_id[self._type]]["CurrentElectricityFlow"]

            elif self._type == 'elecprodcnthigh':
                if self._type in self._dev_id:
                    self._state = float(energy[self._dev_id[self._type]]["CurrentElectricityQuantity"])/1000

            elif self._type == 'elecsolar':
                if 'dev_2.3' in energy:
                    self._state = energy["dev_2.3"]["CurrentElectricityFlow"]
                elif 'dev_4.3' in energy:
                    self._state = energy["dev_4.3"]["CurrentElectricityFlow"]

            elif self._type == 'elecsolarcnt':
                if 'dev_2.3' in energy:
                    self._state = float(energy["dev_2.3"]["CurrentElectricityQuantity"])/1000
                elif 'dev_4.3' in energy:
                    self._state = float(energy["dev_4.3"]["CurrentElectricityQuantity"])/1000

            elif self._type == 'heat':
                if 'dev_2.8' in energy:
                    self._state = float(energy["dev_2.8"]["CurrentHeatQuantity"])/1000
                elif 'dev_4.8' in energy:
                    self._state = float(energy["dev_4.8"]["CurrentHeatQuantity"])/1000

            _LOGGER.debug("Device: {} State: {}".format(self._type, self._state))
