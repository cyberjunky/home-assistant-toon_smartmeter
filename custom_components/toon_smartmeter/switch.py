"""Switch platform for Toon Smart Meter Z-Wave power plugs."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import ToonSmartMeterCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Toon Smart Meter Z-Wave plug switches from a config entry."""
    coordinator: ToonSmartMeterCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Wait for first data update to discover plugs
    if not coordinator.data:
        await coordinator.async_config_entry_first_refresh()

    # Create switch entities for each discovered Z-Wave plug
    entities = []
    for plug_id, plug_info in coordinator.zwave_plugs.items():
        entities.append(
            ToonZWavePlugSwitch(
                coordinator=coordinator,
                entry=entry,
                plug_id=plug_id,
                plug_info=plug_info,
            )
        )
        _LOGGER.debug("Adding Z-Wave plug switch: %s", plug_info.get("name", plug_id))

    if entities:
        async_add_entities(entities)


class ToonZWavePlugSwitch(CoordinatorEntity[ToonSmartMeterCoordinator], SwitchEntity):
    """Representation of a Toon Z-Wave power plug switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ToonSmartMeterCoordinator,
        entry: ConfigEntry,
        plug_id: str,
        plug_info: dict[str, Any],
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)

        self._plug_id = plug_id
        self._plug_info = plug_info
        self._entry = entry

        plug_name = plug_info.get("name", plug_id)
        self._attr_name = plug_name
        self._attr_unique_id = f"{entry.entry_id}_plug_{plug_id}"
        self._attr_icon = "mdi:power-plug"

        # Get device name from options (with fallback to data for migration)
        device_name = entry.options.get(CONF_NAME) or entry.data.get(CONF_NAME, DEFAULT_NAME)

        # Set device info for grouping with main Toon device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"{device_name} Smart Meter",
            manufacturer="Eneco",
            model="Toon Thermostat",
            configuration_url=f"http://{coordinator.host}:{coordinator.port}",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        return self.coordinator.get_plug_state(self._plug_id)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False
        # Check if plug is still in the data
        return self._plug_id in self.coordinator.zwave_plugs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        success = await self.coordinator.async_set_plug_state(self._plug_id, True)
        if success:
            # Request a data refresh to get updated state
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        success = await self.coordinator.async_set_plug_state(self._plug_id, False)
        if success:
            # Request a data refresh to get updated state
            await self.coordinator.async_request_refresh()
