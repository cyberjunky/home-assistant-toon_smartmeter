"""Tests for setting up and unloading the Toon Smart Meter integration."""

from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.toon_smartmeter.const import DOMAIN

from .conftest import DATA_URL, HOST


async def test_setup_and_unload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_toon: AiohttpClientMocker
) -> None:
    """The entry sets up a coordinator with discovered devices and unloads cleanly."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
    assert coordinator.update_interval == timedelta(seconds=10)
    assert coordinator.device_ids["gasusedcnt"] == "dev_2"
    assert "dev_10" in coordinator.zwave_plugs

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    assert mock_config_entry.entry_id not in hass.data[DOMAIN]


async def test_setup_retry_when_offline(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """An unreachable Toon puts the entry into setup retry."""
    aioclient_mock.get(DATA_URL, exc=aiohttp.ClientError())
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_migrate_legacy_unique_ids(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_toon: AiohttpClientMocker
) -> None:
    """Pre-2.0 unique_ids are rewritten so the entity_id (and history) is kept."""
    mock_config_entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    gas = ent_reg.async_get_or_create(
        "sensor", DOMAIN, "Toon _Gas Used Cnt", suggested_object_id="toon_gas_used_cnt"
    )
    water = ent_reg.async_get_or_create(
        "sensor", DOMAIN, "Toon _P1 waterquantity", suggested_object_id="toon_p1_waterquantity"
    )

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entry_id = mock_config_entry.entry_id
    assert ent_reg.async_get(gas.entity_id).unique_id == f"{entry_id}_gasusedcnt"
    assert ent_reg.async_get(gas.entity_id).config_entry_id == entry_id
    assert ent_reg.async_get(water.entity_id).unique_id == f"{entry_id}_waterquantity"
    assert hass.states.get("sensor.toon_gas_used_cnt").state == "5000.0"


async def test_yaml_import(hass: HomeAssistant, mock_toon: AiohttpClientMocker) -> None:
    """Domain-style YAML configuration is imported into a config entry."""
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {"sensor": [{CONF_HOST: HOST}]}})
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].data[CONF_HOST] == HOST
    assert entries[0].state is ConfigEntryState.LOADED
