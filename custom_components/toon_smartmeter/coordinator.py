"""Data coordinator for Toon Smart Meter integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from functools import reduce
from typing import Any

import aiohttp
import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


def safe_get(_dict: dict, keys: list, default: Any = None) -> Any:
    """Safe dictionary get with reduce."""

    def _reducer(d: Any, key: str) -> Any:
        if isinstance(d, dict):
            return d.get(key, default)
        return default

    return reduce(_reducer, keys, _dict)


class ToonSmartMeterCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Toon smart meter data."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        scan_interval: int,
    ) -> None:
        """Initialize the coordinator."""
        self.host = host
        self.port = port
        self._session = session
        self._url = BASE_URL.format(host, port)

        # Device discovery mapping - populated during first update
        self.device_ids: dict[str, str] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Toon device."""
        try:
            async with async_timeout.timeout(10):
                response = await self._session.get(
                    self._url, headers={"Accept-Encoding": "identity"}
                )
                response.raise_for_status()
                data = await response.json(content_type="text/javascript")
                _LOGGER.debug("Data received from Toon: %s", data)

                # Discover devices on first successful fetch
                if not self.device_ids and data:
                    self._discover_devices(data)

                return data
        except aiohttp.ClientError as err:
            raise UpdateFailed(
                f"Error communicating with Toon at {self._url}: {err}"
            ) from err
        except TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching data from {self._url}") from err
        except (TypeError, KeyError, ValueError) as err:
            raise UpdateFailed(f"Error parsing Toon data: {err}") from err

    def _discover_devices(self, energy: dict[str, Any]) -> None:
        """Discover available devices and map to sensor types."""
        for key in energy:
            dev = energy[key]
            dev_type = dev.get("type", "")

            # Gas
            if dev_type in [
                "gas",
                "HAE_METER_v2_1",
                "HAE_METER_v3_1",
                "HAE_METER_v4_1",
            ] and safe_get(energy, [key, "CurrentGasQuantity"], "NaN") != "NaN":
                self.device_ids["gasused"] = key
                self.device_ids["gasusedcnt"] = key

            # Elec low tariff
            if dev_type in [
                "elec_delivered_lt",
                "HAE_METER_v2_5",
                "HAE_METER_v3_6",
                "HAE_METER_v3_5",
                "HAE_METER_v4_6",
                "HAE_METER_HEAT_5",
            ] and safe_get(energy, [key, "CurrentElectricityQuantity"], "NaN") != "NaN":
                self.device_ids["elecusageflowlow"] = key
                self.device_ids["elecusagecntlow"] = key

            # Elec high tariff
            if dev_type in [
                "elec_delivered_nt",
                "HAE_METER_v2_3",
                "HAE_METER_v3_3",
                "HAE_METER_v3_4",
                "HAE_METER_v4_4",
                "HAE_METER_HEAT_3",
            ] and safe_get(energy, [key, "CurrentElectricityQuantity"], "NaN") != "NaN":
                self.device_ids["elecusageflowhigh"] = key
                self.device_ids["elecusagecnthigh"] = key

            # Elec production low
            if dev_type in [
                "elec_received_lt",
                "HAE_METER_v2_6",
                "HAE_METER_v3_7",
                "HAE_METER_v4_7",
            ] and safe_get(energy, [key, "CurrentElectricityQuantity"], "NaN") != "NaN":
                self.device_ids["elecprodflowlow"] = key
                self.device_ids["elecprodcntlow"] = key

            # Elec production high
            if dev_type in [
                "elec_received_nt",
                "HAE_METER_v2_4",
                "HAE_METER_v3_5",
                "HAE_METER_v4_5",
            ] and safe_get(energy, [key, "CurrentElectricityQuantity"], "NaN") != "NaN":
                self.device_ids["elecprodflowhigh"] = key
                self.device_ids["elecprodcnthigh"] = key

            # Solar
            if dev_type in [
                "HAE_METER_v3_3",
                "HAE_METER_v4_3",
            ] and safe_get(energy, [key, "CurrentElectricityQuantity"], "NaN") != "NaN":
                self.device_ids["elecsolar"] = key
                self.device_ids["elecsolarcnt"] = key

            # Heat
            if dev_type in [
                "HAE_METER_v3_8",
                "HAE_METER_v4_8",
                "HAE_METER_HEAT_1",
            ] and safe_get(energy, [key, "CurrentHeatQuantity"], "NaN") != "NaN":
                self.device_ids["heat"] = key

            # Water
            if dev_type in [
                "HAE_METER_v4_9",
            ] and safe_get(energy, [key, "CurrentWaterQuantity"], "NaN") != "NaN":
                self.device_ids["waterquantity"] = key
                self.device_ids["waterflow"] = key

        # Check for pulse devices
        for dev in ["dev_3.2", "dev_2.2", "dev_4.2", "dev_7.2"]:
            if dev in energy:
                self.device_ids["elecusageflowpulse"] = dev
                self.device_ids["elecusagecntpulse"] = dev
                break

        _LOGGER.debug("Discovered devices: %s", self.device_ids)

    def get_sensor_value(self, sensor_key: str) -> float | None:
        """Get the value for a specific sensor."""
        if not self.data:
            return None

        energy = self.data
        device_id = self.device_ids.get(sensor_key)

        try:
            if sensor_key == "gasused" and device_id:
                return float(energy[device_id]["CurrentGasFlow"]) / 1000
            if sensor_key == "gasusedcnt" and device_id:
                return float(energy[device_id]["CurrentGasQuantity"]) / 1000
            if sensor_key == "elecusageflowpulse":
                return self._get_pulse_flow(energy)
            if sensor_key == "elecusagecntpulse":
                value = self._get_pulse_quantity(energy)
                return float(value) / 1000 if value else None
            if sensor_key == "elecusageflowlow" and device_id:
                return self._validate_output(
                    energy[device_id]["CurrentElectricityFlow"]
                )
            if sensor_key == "elecusagecntlow" and device_id:
                return self._validate_output(
                    float(energy[device_id]["CurrentElectricityQuantity"]) / 1000
                )
            if sensor_key == "elecusageflowhigh" and device_id:
                return self._validate_output(
                    energy[device_id]["CurrentElectricityFlow"]
                )
            if sensor_key == "elecusagecnthigh" and device_id:
                return self._validate_output(
                    float(energy[device_id]["CurrentElectricityQuantity"]) / 1000
                )
            if sensor_key == "elecprodflowlow" and device_id:
                return self._validate_output(
                    energy[device_id]["CurrentElectricityFlow"]
                )
            if sensor_key == "elecprodcntlow" and device_id:
                return self._validate_output(
                    float(energy[device_id]["CurrentElectricityQuantity"]) / 1000
                )
            if sensor_key == "elecprodflowhigh" and device_id:
                return self._validate_output(
                    energy[device_id]["CurrentElectricityFlow"]
                )
            if sensor_key == "elecprodcnthigh" and device_id:
                return self._validate_output(
                    float(energy[device_id]["CurrentElectricityQuantity"]) / 1000
                )
            if sensor_key == "elecsolar":
                return self._validate_output(self._get_solar_flow(energy))
            if sensor_key == "elecsolarcnt":
                value = self._get_solar_quantity(energy)
                return self._validate_output(float(value) / 1000) if value else None
            if sensor_key == "heat" and device_id:
                return self._validate_output(
                    float(energy[device_id]["CurrentHeatQuantity"]) / 1000
                )
            if sensor_key == "waterquantity" and device_id:
                return float(energy[device_id]["CurrentWaterQuantity"])
            if sensor_key == "waterflow" and device_id:
                return float(energy[device_id]["CurrentWaterFlow"])
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.debug("Error getting value for %s: %s", sensor_key, err)
            return None

        return None

    def _validate_output(self, value: Any) -> float | None:
        """Return None if the output from the Toon is NaN."""
        try:
            if str(value).lower() == "nan":
                return None
            return float(value)
        except (ValueError, TypeError):
            return None

    def _get_pulse_flow(self, energy: dict[str, Any]) -> float | None:
        """Get electricity flow from pulse devices."""
        for dev in ["dev_3.2", "dev_2.2", "dev_4.2", "dev_7.2"]:
            if dev in energy:
                return self._validate_output(energy[dev]["CurrentElectricityFlow"])
        return None

    def _get_pulse_quantity(self, energy: dict[str, Any]) -> Any:
        """Get electricity quantity from pulse devices."""
        for dev in ["dev_3.2", "dev_2.2", "dev_4.2", "dev_7.2"]:
            if dev in energy:
                return energy[dev]["CurrentElectricityQuantity"]
        return None

    def _get_solar_flow(self, energy: dict[str, Any]) -> float | None:
        """Get solar electricity flow."""
        for dev in ["dev_4.export", "dev_3.export", "dev_7.export", "dev_14.export"]:
            if dev in energy:
                return energy[dev]["CurrentElectricityFlow"]
        device_id = self.device_ids.get("elecsolar")
        if device_id and device_id in energy:
            return energy[device_id]["CurrentElectricityFlow"]
        return None

    def _get_solar_quantity(self, energy: dict[str, Any]) -> Any:
        """Get solar electricity quantity."""
        for dev in ["dev_4.export", "dev_3.export", "dev_7.export", "dev_14.export"]:
            if dev in energy:
                return energy[dev]["CurrentElectricityQuantity"]
        device_id = self.device_ids.get("elecsolarcnt")
        if device_id and device_id in energy:
            return energy[device_id]["CurrentElectricityQuantity"]
        return None
