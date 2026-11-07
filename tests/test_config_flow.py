"""Tests for the Toon Smart Meter config and options flows."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_IMPORT, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.toon_smartmeter.const import BASE_URL, DOMAIN

from .conftest import DATA_URL, ENTRY_OPTIONS, HOST, PORT, device_data


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[AsyncMock]:
    """Prevent created entries from actually being set up."""
    with patch(
        "custom_components.toon_smartmeter.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


async def test_user_flow(
    hass: HomeAssistant, mock_toon: AiohttpClientMocker, mock_setup_entry: AsyncMock
) -> None:
    """A reachable Toon creates an entry; host whitespace is stripped."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: f" {HOST} ", CONF_PORT: PORT, CONF_NAME: "Meter", CONF_SCAN_INTERVAL: 30},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Meter"
    assert result["data"] == {CONF_HOST: HOST, CONF_PORT: PORT}
    assert result["options"] == {CONF_NAME: "Meter", CONF_SCAN_INTERVAL: 30}
    assert result["result"].unique_id == HOST
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize(
    ("mock_kwargs", "error"),
    [
        ({"exc": aiohttp.ClientError()}, "cannot_connect"),
        ({"exc": TimeoutError()}, "cannot_connect"),
        ({"status": 500}, "cannot_connect"),
        ({"text": "not json"}, "invalid_data"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_kwargs: dict,
    error: str,
) -> None:
    """Connection and data errors are shown on the form, and the flow can recover."""
    aioclient_mock.get(DATA_URL, **mock_kwargs)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    aioclient_mock.clear_requests()
    aioclient_mock.get(DATA_URL, json=device_data())
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_unknown_error(hass: HomeAssistant) -> None:
    """An unexpected exception maps to the unknown error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch(
        "custom_components.toon_smartmeter.config_flow.validate_connection",
        side_effect=RuntimeError,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: HOST}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_toon: AiohttpClientMocker
) -> None:
    """A host that is already configured is aborted."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_import_flow(hass: HomeAssistant, mock_toon: AiohttpClientMocker) -> None:
    """YAML config is imported into an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_IMPORT},
        data={CONF_HOST: HOST, CONF_PORT: PORT, CONF_SCAN_INTERVAL: 20},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST, CONF_PORT: PORT}
    assert result["options"] == {CONF_NAME: "Toon", CONF_SCAN_INTERVAL: 20}


async def test_import_flow_aborts(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Import aborts without a host or when the Toon is unreachable."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data={}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_import"

    aioclient_mock.get(DATA_URL, exc=aiohttp.ClientError())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data={CONF_HOST: HOST}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_options_flow_rename(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Changing only the name keeps the address, skips validation and syncs the title."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_HOST: HOST, CONF_PORT: PORT, CONF_NAME: "Meter", CONF_SCAN_INTERVAL: 15},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_NAME: "Meter", CONF_SCAN_INTERVAL: 15}
    assert mock_config_entry.title == "Meter"
    assert aioclient_mock.call_count == 0


async def test_options_flow_change_host(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A new host is validated and stored together with a new unique_id."""
    mock_config_entry.add_to_hass(hass)
    new_host = "192.168.1.21"
    aioclient_mock.get(BASE_URL.format(new_host, PORT), json=device_data())

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_HOST: new_host, CONF_PORT: PORT, **ENTRY_OPTIONS}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.data[CONF_HOST] == new_host
    assert mock_config_entry.unique_id == new_host


async def test_options_flow_host_errors(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """A host used by another entry, or an unreachable host, is rejected."""
    mock_config_entry.add_to_hass(hass)
    MockConfigEntry(domain=DOMAIN, data={CONF_HOST: "10.0.0.2"}, unique_id="10.0.0.2").add_to_hass(
        hass
    )
    aioclient_mock.get(BASE_URL.format("10.0.0.3", PORT), exc=aiohttp.ClientError())

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.2", **ENTRY_OPTIONS}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "already_configured"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.3", **ENTRY_OPTIONS}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert mock_config_entry.data[CONF_HOST] == HOST
