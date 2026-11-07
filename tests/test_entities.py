"""Tests for the Toon Smart Meter sensor and switch entities."""

from urllib.parse import parse_qs

import aiohttp
import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.toon_smartmeter.const import DOMAIN

from .conftest import CONTROL_URL, DATA_URL, device_data


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, entry: MockConfigEntry, platform: str, suffix: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{suffix}"
    )
    assert entity_id is not None, suffix
    return hass.states.get(entity_id).state


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("gasused", "0.12"),
        ("gasusedcnt", "5000.0"),
        ("elecusageflowlow", "300.0"),
        ("elecusagecntlow", "1000.0"),
        ("elecusageflowhigh", "200.0"),
        ("elecusagecnthigh", "2000.0"),
        ("elecusageflow", "500.0"),
        ("elecusagecnt", "3000.0"),
        ("elecprodflowlow", "50.0"),
        ("elecprodcntlow", "300.0"),
        ("elecprodflow", "50.0"),
        ("elecprodcnt", "300.0"),
        # NaN meter, and meters that do not exist in this setup
        ("elecprodflowhigh", STATE_UNAVAILABLE),
        ("elecusageflowpulse", STATE_UNAVAILABLE),
        ("elecsolar", STATE_UNAVAILABLE),
        ("heat", STATE_UNAVAILABLE),
        ("waterquantity", STATE_UNAVAILABLE),
    ],
)
async def test_sensor_states(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_toon: AiohttpClientMocker,
    key: str,
    expected: str,
) -> None:
    """Sensors report converted meter values, or unavailable when not discovered."""
    await _setup(hass, mock_config_entry)

    assert _state(hass, mock_config_entry, "sensor", key) == expected


async def test_plug_entities(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_toon: AiohttpClientMocker
) -> None:
    """A Z-Wave plug gets a power sensor, an energy sensor and a switch."""
    await _setup(hass, mock_config_entry)

    assert _state(hass, mock_config_entry, "sensor", "plug_dev_10_power") == "15.0"
    assert _state(hass, mock_config_entry, "sensor", "plug_dev_10_energy") == "12.345"
    assert _state(hass, mock_config_entry, "switch", "plug_dev_10") == STATE_ON


async def test_sensors_unavailable_after_failed_update(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A failed refresh makes the entities unavailable."""
    aioclient_mock.get(DATA_URL, json=device_data())
    await _setup(hass, mock_config_entry)

    aioclient_mock.clear_requests()
    aioclient_mock.get(DATA_URL, exc=aiohttp.ClientError())
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, mock_config_entry, "sensor", "gasusedcnt") == STATE_UNAVAILABLE
    assert _state(hass, mock_config_entry, "switch", "plug_dev_10") == STATE_UNAVAILABLE


@pytest.mark.parametrize(("service", "state"), [(SERVICE_TURN_ON, "1"), (SERVICE_TURN_OFF, "0")])
async def test_switch_commands(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_toon: AiohttpClientMocker,
    service: str,
    state: str,
) -> None:
    """Turning the plug on/off posts a basicCommand for its node."""
    await _setup(hass, mock_config_entry)
    entity_id = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{mock_config_entry.entry_id}_plug_dev_10"
    )
    mock_toon.clear_requests()
    mock_toon.get(DATA_URL, json=device_data())
    mock_toon.post(CONTROL_URL, text="ok")

    await hass.services.async_call(
        SWITCH_DOMAIN, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    posts = [call for call in mock_toon.mock_calls if call[0] == "POST"]
    assert len(posts) == 1
    assert parse_qs(posts[0][2]) == {
        "action": ["basicCommand"],
        "nodeID": ["10"],
        "state": [state],
    }


async def test_switch_command_failure(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A failing command does not raise and does not trigger a refresh."""
    aioclient_mock.get(DATA_URL, json=device_data())
    aioclient_mock.post(CONTROL_URL, status=500)
    await _setup(hass, mock_config_entry)
    entity_id = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{mock_config_entry.entry_id}_plug_dev_10"
    )
    calls_before = aioclient_mock.call_count

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    assert aioclient_mock.call_count == calls_before + 1
