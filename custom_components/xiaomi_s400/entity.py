"""Base entity helpers."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import Person, S400Coordinator


def scale_device_info(coordinator: S400Coordinator) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.address)},
        connections={(CONNECTION_BLUETOOTH, coordinator.address)},
        name=coordinator.name,
        manufacturer="Xiaomi",
        model="Body Composition Scale S400",
        model_id="MJTZC01YM",
    )


def person_device_info(coordinator: S400Coordinator, person: Person) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.address}_{person.subentry_id}")},
        name=f"{coordinator.name} {person.name}",
        manufacturer="Xiaomi",
        model=f"S400 profile {person.profile_id}",
        via_device=(DOMAIN, coordinator.address),
    )


class S400Entity(Entity):
    """Push-updated entity bound to the coordinator."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: S400Coordinator) -> None:
        self.coordinator = coordinator

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self.async_write_ha_state()
