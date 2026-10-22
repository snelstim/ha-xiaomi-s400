"""Sensors for Xiaomi S400."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import S400ConfigEntry
from .coordinator import Measurement, Person, S400Coordinator, ScaleState
from .entity import S400Entity, person_device_info, scale_device_info

OHM = "Ω"


# ---------------------------------------------------------------- scale-level


@dataclass(frozen=True, kw_only=True)
class ScaleSensorDescription(SensorEntityDescription):
    value_fn: Callable[[ScaleState], Any]


def _last(attr: str) -> Callable[[ScaleState], Any]:
    return lambda s: getattr(s.last_measurement, attr) if s.last_measurement else None


SCALE_SENSORS = (
    ScaleSensorDescription(
        key="live_weight",
        translation_key="live_weight",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=1,
        value_fn=lambda s: s.live_weight,
    ),
    ScaleSensorDescription(
        key="weight",
        translation_key="weight",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=1,
        value_fn=_last("weight_kg"),
    ),
    ScaleSensorDescription(
        key="impedance",
        translation_key="impedance",
        native_unit_of_measurement=OHM,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last("impedance_ohm"),
    ),
    ScaleSensorDescription(
        key="impedance_low",
        translation_key="impedance_low",
        native_unit_of_measurement=OHM,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last("impedance_low_ohm"),
    ),
    ScaleSensorDescription(
        key="heart_rate",
        translation_key="heart_rate",
        native_unit_of_measurement="bpm",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_last("heart_rate"),
    ),
    ScaleSensorDescription(
        key="profile_id",
        translation_key="profile_id",
        value_fn=lambda s: s.last_profile_id,
    ),
    ScaleSensorDescription(
        key="last_measurement",
        translation_key="last_measurement",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last("measured_at"),
    ),
    ScaleSensorDescription(
        key="last_error",
        translation_key="last_error",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.last_error,
    ),
    ScaleSensorDescription(
        key="raw_final",
        translation_key="raw_final",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda s: ",".join(s.last_raw_fields)[:255] if s.last_raw_fields else None,
    ),
)


# ---------------------------------------------------------------- per person


@dataclass(frozen=True, kw_only=True)
class PersonSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Measurement], Any]


def _body(key: str) -> Callable[[Measurement], Any]:
    return lambda m: m.body.get(key)


PERSON_SENSORS = (
    PersonSensorDescription(
        key="weight",
        translation_key="weight",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=1,
        value_fn=lambda m: m.weight_kg,
    ),
    PersonSensorDescription(
        key="impedance",
        translation_key="impedance",
        native_unit_of_measurement=OHM,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.impedance_ohm,
    ),
    PersonSensorDescription(
        key="impedance_low",
        translation_key="impedance_low",
        native_unit_of_measurement=OHM,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.impedance_low_ohm,
    ),
    PersonSensorDescription(
        key="heart_rate",
        translation_key="heart_rate",
        native_unit_of_measurement="bpm",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.heart_rate,
    ),
    PersonSensorDescription(
        key="bmi", translation_key="bmi", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value_fn=_body("bmi"),
    ),
    PersonSensorDescription(
        key="fat_percent", translation_key="fat_percent", native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1, value_fn=_body("fat_percent"),
    ),
    PersonSensorDescription(
        key="water_percent", translation_key="water_percent", native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1, value_fn=_body("water_percent"),
    ),
    PersonSensorDescription(
        key="protein_percent", translation_key="protein_percent", native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1, value_fn=_body("protein_percent"),
    ),
    PersonSensorDescription(
        key="muscle_mass", translation_key="muscle_mass", device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS, state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value_fn=_body("muscle_mass_kg"),
    ),
    PersonSensorDescription(
        key="bone_mass", translation_key="bone_mass", device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS, state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2, value_fn=_body("bone_mass_kg"),
    ),
    PersonSensorDescription(
        key="visceral_fat", translation_key="visceral_fat", state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value_fn=_body("visceral_fat"),
    ),
    PersonSensorDescription(
        key="bmr", translation_key="bmr", native_unit_of_measurement="kcal",
        state_class=SensorStateClass.MEASUREMENT, value_fn=_body("bmr_kcal_day"),
    ),
    PersonSensorDescription(
        key="metabolic_age", translation_key="metabolic_age", native_unit_of_measurement="a",
        state_class=SensorStateClass.MEASUREMENT, value_fn=_body("metabolic_age_years"),
    ),
    PersonSensorDescription(
        key="ideal_weight", translation_key="ideal_weight", device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS, suggested_display_precision=1,
        value_fn=_body("ideal_weight_kg"),
    ),
    PersonSensorDescription(
        key="body_type", translation_key="body_type", device_class=SensorDeviceClass.ENUM,
        options=[
            "obese", "overweight", "thick-set", "lack-exercise", "balanced",
            "balanced-muscular", "skinny", "balanced-skinny", "skinny-muscular",
        ],
        value_fn=_body("body_type_name"),
    ),
    # Only the scale's stored records carry these.
    PersonSensorDescription(
        key="body_score", translation_key="body_score", state_class=SensorStateClass.MEASUREMENT,
        value_fn=_body("body_score"),
    ),
    PersonSensorDescription(
        key="fat_mass", translation_key="fat_mass", device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS, state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1, value_fn=_body("fat_mass_kg"),
    ),
    PersonSensorDescription(
        key="last_measurement", translation_key="last_measurement",
        device_class=SensorDeviceClass.TIMESTAMP, value_fn=lambda m: m.measured_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: S400ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ScaleSensor(coordinator, d) for d in SCALE_SENSORS)
    for person in coordinator.persons.values():
        async_add_entities(
            (PersonSensor(coordinator, person, d) for d in PERSON_SENSORS),
            config_subentry_id=person.subentry_id,
        )


NOT_RESTORED = {"last_error", "raw_final"}


class ScaleSensor(S400Entity, RestoreSensor):
    """Scale-level value; falls back to the last known value after a restart or reload."""

    entity_description: ScaleSensorDescription

    def __init__(self, coordinator: S400Coordinator, description: ScaleSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = scale_device_info(coordinator)
        self._restored: Any = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.entity_description.key in NOT_RESTORED:
            return
        if (last := await self.async_get_last_sensor_data()) is not None:
            value = last.native_value
            if self.device_class == SensorDeviceClass.TIMESTAMP and isinstance(value, str):
                value = dt_util.parse_datetime(value)
            self._restored = value

    @property
    def native_value(self) -> Any:
        value = self.entity_description.value_fn(self.coordinator.state)
        return self._restored if value is None else value


class PersonSensor(S400Entity, RestoreSensor):
    """Per-person value; restored after restart, updated only by that person's measurements."""

    entity_description: PersonSensorDescription

    def __init__(self, coordinator: S400Coordinator, person: Person, description: PersonSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.person = person
        self._attr_unique_id = f"{coordinator.address}_{person.subentry_id}_{description.key}"
        self._attr_device_info = person_device_info(coordinator, person)
        self._measurement: Measurement | None = None
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            value = last.native_value
            if self.device_class == SensorDeviceClass.TIMESTAMP and isinstance(value, str):
                value = dt_util.parse_datetime(value)
            self._attr_native_value = value

    def _handle_update(self) -> None:
        measurement = self.coordinator.person_measurements.get(self.person.subentry_id)
        if measurement is None:
            return
        value = self.entity_description.value_fn(measurement)
        if measurement is self._measurement and value == self._attr_native_value:
            return
        if measurement is self._measurement and value is None:
            return
        self._measurement = measurement
        self._attr_native_value = value
        self.async_write_ha_state()
