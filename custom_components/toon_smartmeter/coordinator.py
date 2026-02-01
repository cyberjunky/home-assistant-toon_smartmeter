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

from .const import BASE_URL, DOMAIN, ZWAVE_CONTROL_URL

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

        # Z-Wave power plugs - key is device id (e.g., "dev_4"), value is plug info
        self.zwave_plugs: dict[str, dict[str, Any]] = {}

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

                return dict(data)
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error communicating with Toon at {self._url}: {err}") from err
        except TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching data from {self._url}") from err
        except (TypeError, KeyError, ValueError) as err:
            raise UpdateFailed(f"Error parsing Toon data: {err}") from err

    def _discover_devices(self, energy: dict[str, Any]) -> None:
        """Discover available devices using data-driven detection.

        This method uses a two-phase approach:
        1. First, detect by semantic type names (most reliable)
        2. Then, detect by data field presence for HAE_METER types
        """
        # Track electricity meters for computing totals
        elec_delivered_meters: list[str] = []
        elec_produced_meters: list[str] = []

        for key in energy:
            dev = energy[key]
            dev_type = dev.get("type", "")
            dev_name = dev.get("name", "").lower()

            # === GAS DETECTION ===
            if self._has_valid_gas(energy, key):
                if dev_type in ["gas", "HAE_METER_v2_1", "HAE_METER_v3_1", "HAE_METER_v4_1"]:
                    self.device_ids["gasused"] = key
                    self.device_ids["gasusedcnt"] = key
                    _LOGGER.debug("Gas meter detected: %s (type: %s)", key, dev_type)

            # === ELECTRICITY DETECTION ===
            if self._has_valid_electricity(energy, key):
                # Phase 1: Semantic type names (most reliable)
                if "elec_delivered_lt" in dev_type or "elec_delivered_lt" in dev_name:
                    self.device_ids["elecusageflowlow"] = key
                    self.device_ids["elecusagecntlow"] = key
                    elec_delivered_meters.append(key)
                    _LOGGER.debug("Elec delivered low tariff: %s", key)

                elif "elec_delivered_nt" in dev_type or "elec_delivered_nt" in dev_name:
                    self.device_ids["elecusageflowhigh"] = key
                    self.device_ids["elecusagecnthigh"] = key
                    elec_delivered_meters.append(key)
                    _LOGGER.debug("Elec delivered high tariff: %s", key)

                elif "elec_received_lt" in dev_type or "elec_received_lt" in dev_name:
                    self.device_ids["elecprodflowlow"] = key
                    self.device_ids["elecprodcntlow"] = key
                    elec_produced_meters.append(key)
                    _LOGGER.debug("Elec produced low tariff: %s", key)

                elif "elec_received_nt" in dev_type or "elec_received_nt" in dev_name:
                    self.device_ids["elecprodflowhigh"] = key
                    self.device_ids["elecprodcnthigh"] = key
                    elec_produced_meters.append(key)
                    _LOGGER.debug("Elec produced high tariff: %s", key)

                # Phase 2: HAE_METER type suffix patterns (fallback)
                elif dev_type.startswith("HAE_METER"):
                    self._classify_hae_meter(
                        key, dev_type, elec_delivered_meters, elec_produced_meters
                    )

            # === SOLAR DETECTION ===
            # Solar can be: HAE_METER_v3_3, HAE_METER_v4_3, or semantic type "elec_solar"
            if dev_type in ["HAE_METER_v3_3", "HAE_METER_v4_3", "elec_solar"]:
                if self._has_valid_electricity(energy, key):
                    self.device_ids["elecsolar"] = key
                    self.device_ids["elecsolarcnt"] = key
                    _LOGGER.debug("Solar meter detected: %s (type: %s)", key, dev_type)

            # === HEAT DETECTION ===
            if self._has_valid_heat(energy, key):
                if dev_type in ["HAE_METER_v3_8", "HAE_METER_v4_8", "HAE_METER_HEAT_1"]:
                    self.device_ids["heat"] = key
                    _LOGGER.debug("Heat meter detected: %s", key)

            # === WATER DETECTION ===
            if self._has_valid_water(energy, key):
                if dev_type in ["HAE_METER_v4_9"]:
                    self.device_ids["waterquantity"] = key
                    self.device_ids["waterflow"] = key
                    _LOGGER.debug("Water meter detected: %s", key)

            # === Z-WAVE POWERPLUG DETECTION ===
            # Plugs have TargetStatus (for on/off control) AND electricity data
            # This distinguishes them from meters which don't have TargetStatus
            if self._is_zwave_plug(energy, key):
                plug_name = dev.get("DeviceName") or dev.get("name", key)
                self.zwave_plugs[key] = {
                    "name": plug_name,
                    "uuid": dev.get("uuid", ""),
                    "type": dev_type,
                    "internal_address": dev.get("internalAddress", ""),
                }
                _LOGGER.debug("Z-Wave plug detected: %s (%s, type: %s)", key, plug_name, dev_type)

        # Check for pulse devices
        for dev in ["dev_3.2", "dev_2.2", "dev_4.2", "dev_7.2"]:
            if dev in energy and self._has_valid_electricity(energy, dev):
                self.device_ids["elecusageflowpulse"] = dev
                self.device_ids["elecusagecntpulse"] = dev
                _LOGGER.debug("Pulse meter detected: %s", dev)
                break

        # Store meter lists for total calculations
        if elec_delivered_meters:
            self.device_ids["_elec_delivered_meters"] = ",".join(elec_delivered_meters)
            # Enable total usage sensors
            self.device_ids["elecusageflow"] = "total"
            self.device_ids["elecusagecnt"] = "total"

        if elec_produced_meters:
            self.device_ids["_elec_produced_meters"] = ",".join(elec_produced_meters)
            # Enable total production sensors
            self.device_ids["elecprodflow"] = "total"
            self.device_ids["elecprodcnt"] = "total"

        _LOGGER.debug("Discovered devices: %s", self.device_ids)

    def _classify_hae_meter(
        self,
        key: str,
        dev_type: str,
        elec_delivered_meters: list[str],
        elec_produced_meters: list[str],
    ) -> None:
        """Classify HAE_METER devices by their type suffix.

        Known mappings by meter version:
        - v2: 3=high delivered, 4=high produced, 5=low delivered, 6=low produced
        - v3: 3=solar, 4=high delivered, 5=low delivered, 6=high produced, 7=low produced
        - v4: 3=solar, 4=high delivered, 5=high produced, 6=low delivered, 7=low produced
        """
        # Extract version and suffix (e.g., "HAE_METER_v4_5" -> "v4", "5")
        parts = dev_type.split("_")
        if len(parts) < 4:
            return

        version = parts[2]  # "v2", "v3", or "v4"
        suffix = parts[-1]

        # Version 2 has a specific mapping
        if version == "v2":
            if suffix == "3":
                self._set_delivered_high(key, dev_type, elec_delivered_meters)
            elif suffix == "4":
                self._set_produced_high(key, dev_type, elec_produced_meters)
            elif suffix == "5":
                self._set_delivered_low(key, dev_type, elec_delivered_meters)
            elif suffix == "6":
                self._set_produced_low(key, dev_type, elec_produced_meters)
            return

        # Version 3 mapping (same as v4 based on issue #7 data)
        # v3_4 = verbruik hoog (high delivered)
        # v3_5 = teruglevering hoog (high produced)
        # v3_6 = verbruik laag (low delivered)
        # v3_7 = teruglevering laag (low produced)
        if version == "v3":
            if suffix == "4":
                self._set_delivered_high(key, dev_type, elec_delivered_meters)
            elif suffix == "5":
                self._set_produced_high(key, dev_type, elec_produced_meters)
            elif suffix == "6":
                self._set_delivered_low(key, dev_type, elec_delivered_meters)
            elif suffix == "7":
                self._set_produced_low(key, dev_type, elec_produced_meters)
            return

        # Version 4 mapping (and fallback for unknown versions)
        if suffix == "4":
            self._set_delivered_high(key, dev_type, elec_delivered_meters)
        elif suffix == "5":
            self._set_produced_high(key, dev_type, elec_produced_meters)
        elif suffix == "6":
            self._set_delivered_low(key, dev_type, elec_delivered_meters)
        elif suffix == "7":
            self._set_produced_low(key, dev_type, elec_produced_meters)

    def _set_delivered_high(
        self, key: str, dev_type: str, meters: list[str]
    ) -> None:
        """Set high tariff delivered (consumption) meter."""
        if "elecusageflowhigh" not in self.device_ids:
            self.device_ids["elecusageflowhigh"] = key
            self.device_ids["elecusagecnthigh"] = key
            meters.append(key)
            _LOGGER.debug("HAE meter high delivered: %s (%s)", key, dev_type)

    def _set_delivered_low(
        self, key: str, dev_type: str, meters: list[str]
    ) -> None:
        """Set low tariff delivered (consumption) meter."""
        if "elecusageflowlow" not in self.device_ids:
            self.device_ids["elecusageflowlow"] = key
            self.device_ids["elecusagecntlow"] = key
            meters.append(key)
            _LOGGER.debug("HAE meter low delivered: %s (%s)", key, dev_type)

    def _set_produced_high(
        self, key: str, dev_type: str, meters: list[str]
    ) -> None:
        """Set high tariff produced (return to grid) meter."""
        if "elecprodflowhigh" not in self.device_ids:
            self.device_ids["elecprodflowhigh"] = key
            self.device_ids["elecprodcnthigh"] = key
            meters.append(key)
            _LOGGER.debug("HAE meter high produced: %s (%s)", key, dev_type)

    def _set_produced_low(
        self, key: str, dev_type: str, meters: list[str]
    ) -> None:
        """Set low tariff produced (return to grid) meter."""
        if "elecprodflowlow" not in self.device_ids:
            self.device_ids["elecprodflowlow"] = key
            self.device_ids["elecprodcntlow"] = key
            meters.append(key)
            _LOGGER.debug("HAE meter low produced: %s (%s)", key, dev_type)

    def _has_valid_gas(self, energy: dict[str, Any], key: str) -> bool:
        """Check if device has valid gas data."""
        value = safe_get(energy, [key, "CurrentGasQuantity"], "NaN")
        return value != "NaN" and str(value).lower() != "nan"

    def _has_valid_electricity(self, energy: dict[str, Any], key: str) -> bool:
        """Check if device has valid electricity data."""
        value = safe_get(energy, [key, "CurrentElectricityQuantity"], "NaN")
        return value != "NaN" and str(value).lower() != "nan"

    def _has_valid_heat(self, energy: dict[str, Any], key: str) -> bool:
        """Check if device has valid heat data."""
        value = safe_get(energy, [key, "CurrentHeatQuantity"], "NaN")
        return value != "NaN" and str(value).lower() != "nan"

    def _has_valid_water(self, energy: dict[str, Any], key: str) -> bool:
        """Check if device has valid water data."""
        value = safe_get(energy, [key, "CurrentWaterQuantity"], "NaN")
        return value != "NaN" and str(value).lower() != "nan"

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
                return self._validate_output(energy[device_id]["CurrentElectricityFlow"])
            if sensor_key == "elecusagecntlow" and device_id:
                return self._validate_output(
                    float(energy[device_id]["CurrentElectricityQuantity"]) / 1000
                )
            if sensor_key == "elecusageflowhigh" and device_id:
                return self._validate_output(energy[device_id]["CurrentElectricityFlow"])
            if sensor_key == "elecusagecnthigh" and device_id:
                return self._validate_output(
                    float(energy[device_id]["CurrentElectricityQuantity"]) / 1000
                )
            if sensor_key == "elecprodflowlow" and device_id:
                return self._validate_output(energy[device_id]["CurrentElectricityFlow"])
            if sensor_key == "elecprodcntlow" and device_id:
                return self._validate_output(
                    float(energy[device_id]["CurrentElectricityQuantity"]) / 1000
                )
            if sensor_key == "elecprodflowhigh" and device_id:
                return self._validate_output(energy[device_id]["CurrentElectricityFlow"])
            if sensor_key == "elecprodcnthigh" and device_id:
                return self._validate_output(
                    float(energy[device_id]["CurrentElectricityQuantity"]) / 1000
                )
            # Total electricity usage (sum of high + low tariffs)
            if sensor_key == "elecusageflow":
                return self._get_total_electricity_flow("_elec_delivered_meters")
            if sensor_key == "elecusagecnt":
                return self._get_total_electricity_quantity("_elec_delivered_meters")
            # Total electricity production (sum of high + low tariffs)
            if sensor_key == "elecprodflow":
                return self._get_total_electricity_flow("_elec_produced_meters")
            if sensor_key == "elecprodcnt":
                return self._get_total_electricity_quantity("_elec_produced_meters")
            if sensor_key == "elecsolar":
                return self._validate_output(self._get_solar_flow(energy))
            if sensor_key == "elecsolarcnt":
                value = self._get_solar_quantity(energy)
                return self._validate_output(float(value) / 1000) if value else None
            if sensor_key == "heat" and device_id:
                return self._validate_output(float(energy[device_id]["CurrentHeatQuantity"]) / 1000)
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
                return float(energy[dev]["CurrentElectricityFlow"])
        device_id = self.device_ids.get("elecsolar")
        if device_id and device_id in energy:
            return float(energy[device_id]["CurrentElectricityFlow"])
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

    def _get_total_electricity_flow(self, meters_key: str) -> float | None:
        """Get total electricity flow by summing all meters of a type.

        Args:
            meters_key: The device_ids key that contains comma-separated meter IDs
        """
        if not self.data:
            return None

        meters_str = self.device_ids.get(meters_key)
        if not meters_str:
            return None

        energy = self.data
        total = 0.0
        has_valid = False

        for meter_id in meters_str.split(","):
            if meter_id in energy:
                value = self._validate_output(energy[meter_id].get("CurrentElectricityFlow"))
                if value is not None:
                    total += value
                    has_valid = True

        return total if has_valid else None

    def _get_total_electricity_quantity(self, meters_key: str) -> float | None:
        """Get total electricity quantity by summing all meters of a type.

        Args:
            meters_key: The device_ids key that contains comma-separated meter IDs
        """
        if not self.data:
            return None

        meters_str = self.device_ids.get(meters_key)
        if not meters_str:
            return None

        energy = self.data
        total = 0.0
        has_valid = False

        for meter_id in meters_str.split(","):
            if meter_id in energy:
                value = self._validate_output(energy[meter_id].get("CurrentElectricityQuantity"))
                if value is not None:
                    total += value / 1000  # Convert Wh to kWh
                    has_valid = True

        return total if has_valid else None

    def _is_zwave_plug(self, energy: dict[str, Any], key: str) -> bool:
        """Check if device is a Z-Wave power plug.

        Z-Wave plugs are identified by having both:
        - TargetStatus field (for on/off control) - meters don't have this
        - CurrentElectricityFlow field (for power measurement)
        """
        dev = energy.get(key, {})
        has_target_status = "TargetStatus" in dev
        has_elec_flow = "CurrentElectricityFlow" in dev
        # Exclude HAE_METER types which are not plugs
        dev_type = dev.get("type", "")
        is_meter = dev_type.startswith("HAE_METER")
        return has_target_status and has_elec_flow and not is_meter

    def get_plug_power(self, plug_id: str) -> float | None:
        """Get current power usage of a Z-Wave plug in Watts."""
        if not self.data or plug_id not in self.data:
            return None
        try:
            value = self.data[plug_id].get("CurrentElectricityFlow")
            return self._validate_output(value)
        except (KeyError, TypeError, ValueError):
            return None

    def get_plug_energy(self, plug_id: str) -> float | None:
        """Get total energy consumption of a Z-Wave plug in kWh."""
        if not self.data or plug_id not in self.data:
            return None
        try:
            value = self.data[plug_id].get("CurrentElectricityQuantity")
            validated = self._validate_output(value)
            return validated / 1000 if validated is not None else None
        except (KeyError, TypeError, ValueError):
            return None

    def get_plug_state(self, plug_id: str) -> bool | None:
        """Get the on/off state of a Z-Wave plug."""
        if not self.data or plug_id not in self.data:
            return None
        try:
            target_status = self.data[plug_id].get("TargetStatus")
            if target_status is None:
                return None
            return str(target_status) == "1"
        except (KeyError, TypeError):
            return None

    async def async_set_plug_state(self, plug_id: str, state: bool) -> bool:
        """Turn a Z-Wave plug on or off.

        Args:
            plug_id: The device ID (e.g., "dev_4")
            state: True for on, False for off

        Returns:
            True if command was sent successfully, False otherwise
        """
        plug_info = self.zwave_plugs.get(plug_id)
        if not plug_info:
            _LOGGER.error("Unknown Z-Wave plug: %s", plug_id)
            return False

        node_id = plug_info.get("internal_address", "")
        if not node_id:
            _LOGGER.error("No internal address for plug: %s", plug_id)
            return False

        url = ZWAVE_CONTROL_URL.format(self.host, self.port)
        state_value = "1" if state else "0"
        data = f"action=basicCommand&nodeID={node_id}&state={state_value}"

        try:
            async with async_timeout.timeout(10):
                response = await self._session.post(
                    url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                _LOGGER.debug("Set plug %s state to %s", plug_id, state)
                # Note: We don't call GetBasic here to avoid race conditions.
                # The normal coordinator refresh will pick up the new state.
                return True
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.error("Error setting plug %s state: %s", plug_id, err)
            return False

    async def async_refresh_plug_state(self, plug_id: str) -> None:
        """Refresh the state of a Z-Wave plug.

        This is needed because TargetStatus doesn't update immediately after
        sending a basicCommand. We need to send a GetBasic command to trigger
        the status update.
        """
        plug_info = self.zwave_plugs.get(plug_id)
        if not plug_info:
            return

        node_id = plug_info.get("internal_address", "")
        if not node_id:
            return

        url = ZWAVE_CONTROL_URL.format(self.host, self.port)
        data = f"action=GetBasic&nodeID={node_id}"

        try:
            async with async_timeout.timeout(10):
                response = await self._session.post(
                    url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                _LOGGER.debug("Refreshed plug %s state", plug_id)
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Error refreshing plug %s state: %s", plug_id, err)

