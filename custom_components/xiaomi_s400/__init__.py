"""Xiaomi S400: real-time weight and body composition over BLE GATT."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import S400Coordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

type S400ConfigEntry = ConfigEntry[S400Coordinator]


async def async_setup_entry(hass: HomeAssistant, entry: S400ConfigEntry) -> bool:
    """Set up from a config entry."""
    coordinator = S400Coordinator(hass, entry)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: S400ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: S400ConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
