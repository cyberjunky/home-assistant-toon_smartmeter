"""Tests for device discovery and value extraction in the coordinator."""

from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.toon_smartmeter.coordinator import ToonSmartMeterCoordinator


def _meter(dev_type: str, flow: str, quantity: str) -> dict[str, str]:
    return {
        "type": dev_type,
        "CurrentElectricityFlow": flow,
        "CurrentElectricityQuantity": quantity,
    }


def _coordinator(hass: HomeAssistant, data: dict[str, Any]) -> ToonSmartMeterCoordinator:
    coordinator = ToonSmartMeterCoordinator(
        hass=hass, session=MagicMock(), host="toon", port=80, scan_interval=10
    )
    coordinator._discover_devices(data)
    coordinator.data = data
    return coordinator


async def test_hae_meter_v4_discovery(hass: HomeAssistant) -> None:
    """HAE_METER_v4 devices are mapped to gas, tariff, solar, heat, water and pulse sensors."""
    data = {
        "dev_3.1": {"type": "HAE_METER_v4_1", "CurrentGasFlow": "50", "CurrentGasQuantity": "1000"},
        "dev_3.3": _meter("HAE_METER_v4_3", "1200", "800000"),
        "dev_3.4": _meter("HAE_METER_v4_4", "100", "1000"),
        "dev_3.5": _meter("HAE_METER_v4_5", "10", "2000"),
        "dev_3.6": _meter("HAE_METER_v4_6", "200", "3000"),
        "dev_3.7": _meter("HAE_METER_v4_7", "20", "4000"),
        "dev_3.8": {"type": "HAE_METER_v4_8", "CurrentHeatQuantity": "5000"},
        "dev_3.9": {
            "type": "HAE_METER_v4_9",
            "CurrentWaterQuantity": "123",
            "CurrentWaterFlow": "4",
        },
        "dev_2.2": _meter("elec", "450", "9000"),
    }
    coordinator = _coordinator(hass, data)

    assert coordinator.device_ids["elecusageflowhigh"] == "dev_3.4"
    assert coordinator.device_ids["elecprodflowhigh"] == "dev_3.5"
    assert coordinator.device_ids["elecusageflowlow"] == "dev_3.6"
    assert coordinator.device_ids["elecprodflowlow"] == "dev_3.7"

    expected = {
        "gasused": 0.05,
        "gasusedcnt": 1.0,
        "elecusageflow": 300.0,
        "elecusagecnt": 4.0,
        "elecprodflow": 30.0,
        "elecprodcnt": 6.0,
        "elecsolar": 1200.0,
        "elecsolarcnt": 800.0,
        "heat": 5.0,
        "waterquantity": 123.0,
        "waterflow": 4.0,
        "elecusageflowpulse": 450.0,
        "elecusagecntpulse": 9.0,
    }
    for key, value in expected.items():
        assert coordinator.get_sensor_value(key) == pytest.approx(value), key


async def test_hae_meter_v2_discovery(hass: HomeAssistant) -> None:
    """HAE_METER_v2 uses a different suffix mapping."""
    data = {
        "dev_4.3": _meter("HAE_METER_v2_3", "1", "1"),
        "dev_4.4": _meter("HAE_METER_v2_4", "2", "2"),
        "dev_4.5": _meter("HAE_METER_v2_5", "3", "3"),
        "dev_4.6": _meter("HAE_METER_v2_6", "4", "4"),
    }
    coordinator = _coordinator(hass, data)

    assert coordinator.device_ids["elecusageflowhigh"] == "dev_4.3"
    assert coordinator.device_ids["elecprodflowhigh"] == "dev_4.4"
    assert coordinator.device_ids["elecusageflowlow"] == "dev_4.5"
    assert coordinator.device_ids["elecprodflowlow"] == "dev_4.6"


async def test_missing_values(hass: HomeAssistant) -> None:
    """Missing data and NaN values yield None instead of raising."""
    coordinator = _coordinator(hass, {"dev_9": _meter("elec_delivered_lt", "NaN", "1000")})

    assert coordinator.get_sensor_value("elecusageflowlow") is None
    assert coordinator.get_sensor_value("elecusagecntlow") == 1.0
    assert coordinator.get_sensor_value("gasused") is None
    assert coordinator.get_plug_state("dev_missing") is None

    coordinator.data = {}
    assert coordinator.get_sensor_value("elecusagecntlow") is None
