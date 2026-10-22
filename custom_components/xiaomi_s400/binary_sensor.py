"""Binary sensors for Xiaomi S400."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import S400ConfigEntry
from .coordinator import S400Coordinator, ScaleState
from .entity import S400Entity, scale_device_info


@dataclass(frozen=True, kw_only=True)
class S400BinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[ScaleState], bool]


DESCRIPTIONS = (
    S400BinaryDescription(
        key="on_scale",
        translation_key="on_scale",
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        value_fn=lambda s: s.on_scale,
    ),
    S400BinaryDescription(
        key="stable",
        translation_key="stable",
        value_fn=lambda s: s.stable,
    ),
    S400BinaryDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.connected,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: S400ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(S400BinarySensor(coordinator, d) for d in DESCRIPTIONS)


class S400BinarySensor(S400Entity, BinarySensorEntity):
    entity_description: S400BinaryDescription

    def __init__(self, coordinator: S400Coordinator, description: S400BinaryDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = scale_device_info(coordinator)

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.state)
