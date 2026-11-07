"""Fixtures for Toon Smart Meter tests."""

from typing import Any

import pytest
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.toon_smartmeter.const import BASE_URL, DOMAIN, ZWAVE_CONTROL_URL

HOST = "192.168.1.20"
PORT = 80
DATA_URL = BASE_URL.format(HOST, PORT)
CONTROL_URL = ZWAVE_CONTROL_URL.format(HOST, PORT)

ENTRY_DATA = {CONF_HOST: HOST, CONF_PORT: PORT}
ENTRY_OPTIONS = {CONF_NAME: "Toon", CONF_SCAN_INTERVAL: 10}


def device_data() -> dict[str, Any]:
    """Return a getDevices.json response with gas, electricity and a Z-Wave plug."""
    return {
        "dev_2": {
            "type": "gas",
            "name": "gas",
            "CurrentGasFlow": "120",
            "CurrentGasQuantity": "5000000",
        },
        "dev_9.1": {
            "type": "elec_delivered_lt",
            "CurrentElectricityFlow": "300",
            "CurrentElectricityQuantity": "1000000",
        },
        "dev_9.3": {
            "type": "elec_delivered_nt",
            "CurrentElectricityFlow": "200",
            "CurrentElectricityQuantity": "2000000",
        },
        "dev_9.4": {
            "type": "elec_received_lt",
            "CurrentElectricityFlow": "50",
            "CurrentElectricityQuantity": "300000",
        },
        "dev_9.5": {
            "type": "elec_received_nt",
            "CurrentElectricityFlow": "NaN",
            "CurrentElectricityQuantity": "NaN",
        },
        "dev_10": {
            "type": "FGWP011",
            "DeviceName": "Washer",
            "uuid": "plug-uuid",
            "internalAddress": "10",
            "TargetStatus": "1",
            "CurrentElectricityFlow": "15",
            "CurrentElectricityQuantity": "12345",
        },
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading of the custom integration in all tests."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mocked config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Toon",
        data=dict(ENTRY_DATA),
        options=dict(ENTRY_OPTIONS),
        unique_id=HOST,
    )


@pytest.fixture
def mock_toon(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Serve device data and accept Z-Wave commands on the mocked HTTP client."""
    aioclient_mock.get(DATA_URL, json=device_data())
    aioclient_mock.post(CONTROL_URL, text="ok")
    return aioclient_mock
