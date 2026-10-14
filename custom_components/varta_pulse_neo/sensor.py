"""Sensor platform for the VARTA pulse neo."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfApparentPower,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import VartaData
from .const import BATTERY_STATES
from .coordinator import ENERGY_COUNTERS, VartaConfigEntry, grid_power
from .entity import VartaEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class VartaSensorEntityDescription(SensorEntityDescription):
    """Describes a VARTA sensor."""

    value_fn: Callable[[VartaData], int | float | str | None]


def _full_cycles(data: VartaData) -> float | None:
    # Equivalent full cycles: total charged energy divided by the capacity.
    if not data.installed_capacity:
        return None
    return round(data.total_charged_energy / data.installed_capacity, 2)


SENSORS: tuple[VartaSensorEntityDescription, ...] = (
    VartaSensorEntityDescription(
        key="soc",
        translation_key="soc",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.soc,
    ),
    VartaSensorEntityDescription(
        key="battery_power",
        translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.active_power,
    ),
    VartaSensorEntityDescription(
        key="battery_charge_power",
        translation_key="battery_charge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: max(d.active_power, 0),
    ),
    VartaSensorEntityDescription(
        key="battery_discharge_power",
        translation_key="battery_discharge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: max(-d.active_power, 0),
    ),
    VartaSensorEntityDescription(
        key="apparent_power",
        translation_key="apparent_power",
        device_class=SensorDeviceClass.APPARENT_POWER,
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.apparent_power,
    ),
    VartaSensorEntityDescription(
        key="grid_power",
        translation_key="grid_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=grid_power,
    ),
    VartaSensorEntityDescription(
        key="grid_import_power",
        translation_key="grid_import_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: max(grid_power(d), 0),
    ),
    VartaSensorEntityDescription(
        key="grid_export_power",
        translation_key="grid_export_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: max(-grid_power(d), 0),
    ),
    VartaSensorEntityDescription(
        key="pv_sensor_power",
        translation_key="pv_sensor_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.pv_sensor_power,
    ),
    VartaSensorEntityDescription(
        key="state",
        translation_key="state",
        device_class=SensorDeviceClass.ENUM,
        options=list(BATTERY_STATES.values()),
        value_fn=lambda d: BATTERY_STATES.get(d.state),
    ),
    VartaSensorEntityDescription(
        key="total_charged_energy",
        translation_key="total_charged_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.total_charged_energy,
    ),
    VartaSensorEntityDescription(
        key="full_cycles",
        translation_key="full_cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        value_fn=_full_cycles,
    ),
    VartaSensorEntityDescription(
        key="installed_capacity",
        translation_key="installed_capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.installed_capacity,
    ),
    VartaSensorEntityDescription(
        key="number_modules",
        translation_key="number_modules",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.number_modules,
    ),
    VartaSensorEntityDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.error_code,
    ),
)


ENERGY_SENSORS: tuple[SensorEntityDescription, ...] = tuple(
    SensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
    )
    for key in ENERGY_COUNTERS
)

EFFICIENCY_SENSOR = SensorEntityDescription(
    key="efficiency",
    translation_key="efficiency",
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=1,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VartaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        VartaSensor(coordinator, description) for description in SENSORS
    ]
    entities.extend(
        VartaEnergySensor(coordinator, description) for description in ENERGY_SENSORS
    )
    entities.append(VartaEfficiencySensor(coordinator, EFFICIENCY_SENSOR))
    async_add_entities(entities)


class VartaSensor(VartaEntity, SensorEntity):
    """A sensor reading a value directly from the device."""

    entity_description: VartaSensorEntityDescription

    @property
    def native_value(self) -> int | float | str | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Unavailable if the value is not provided by the device."""
        return super().available and self.native_value is not None


class VartaEnergySensor(VartaEntity, SensorEntity):
    """Energy counter (kWh) integrated from a power value by the coordinator."""

    @property
    def native_value(self) -> float:
        """Return the accumulated energy."""
        return round(self.coordinator.energy[self.entity_description.key], 4)


class VartaEfficiencySensor(VartaEntity, SensorEntity):
    """Round-trip efficiency of the battery."""

    @property
    def native_value(self) -> float | None:
        """Return the efficiency in percent."""
        value = self.coordinator.efficiency
        return None if value is None else round(value, 2)
