"""Sensor platform for the VARTA pulse neo."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from homeassistant.components.sensor import (
    RestoreSensor,
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import VartaData
from .const import BATTERY_STATES, DOMAIN, MANUFACTURER, MODEL
from .coordinator import VartaConfigEntry, VartaCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class VartaSensorEntityDescription(SensorEntityDescription):
    """Describes a VARTA sensor."""

    value_fn: Callable[[VartaData], int | float | str | None]


def _grid_power(data: VartaData) -> int:
    # The device reports feed-in as positive; Home Assistant uses import positive.
    return -data.grid_power


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
        value_fn=_grid_power,
    ),
    VartaSensorEntityDescription(
        key="grid_import_power",
        translation_key="grid_import_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: max(_grid_power(d), 0),
    ),
    VartaSensorEntityDescription(
        key="grid_export_power",
        translation_key="grid_export_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: max(-_grid_power(d), 0),
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


@dataclass(frozen=True, kw_only=True)
class VartaEnergySensorEntityDescription(SensorEntityDescription):
    """Describes an energy counter integrated from a power value."""

    power_fn: Callable[[VartaData], float]


# The device has no import/export/discharge counters, so these are integrated
# from the polled power values (trapezoidal rule) for the Energy dashboard.
ENERGY_SENSORS: tuple[VartaEnergySensorEntityDescription, ...] = (
    VartaEnergySensorEntityDescription(
        key="battery_charged_energy",
        translation_key="battery_charged_energy",
        power_fn=lambda d: max(d.active_power, 0),
    ),
    VartaEnergySensorEntityDescription(
        key="battery_discharged_energy",
        translation_key="battery_discharged_energy",
        power_fn=lambda d: max(-d.active_power, 0),
    ),
    VartaEnergySensorEntityDescription(
        key="grid_import_energy",
        translation_key="grid_import_energy",
        power_fn=lambda d: max(_grid_power(d), 0),
    ),
    VartaEnergySensorEntityDescription(
        key="grid_export_energy",
        translation_key="grid_export_energy",
        power_fn=lambda d: max(-_grid_power(d), 0),
    ),
)

# Do not bridge gaps longer than this (e.g. device offline) with a straight line.
MAX_INTEGRATION_GAP = 300  # seconds


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
    async_add_entities(entities)


class VartaEntity(CoordinatorEntity[VartaCoordinator]):
    """Common base for VARTA entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: VartaCoordinator, description: SensorEntityDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        info = coordinator.device_info
        identifier = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{identifier}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=entry.title,
            serial_number=info.serial or None,
            sw_version=info.software_version_ems or None,
            hw_version=info.software_version_inverter or None,
        )


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


class VartaEnergySensor(VartaEntity, RestoreSensor):
    """Energy counter (kWh) integrated from a power value."""

    entity_description: VartaEnergySensorEntityDescription
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: VartaCoordinator,
        description: VartaEnergySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description)
        self._energy = Decimal(0)
        self._last_power: float | None = None
        self._last_time: datetime | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last counter value."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            try:
                self._energy = Decimal(str(last.native_value))
            except ArithmeticError:
                self._energy = Decimal(0)
        self._integrate()

    @property
    def native_value(self) -> float:
        """Return the accumulated energy."""
        return float(round(self._energy, 4))

    @callback
    def _handle_coordinator_update(self) -> None:
        self._integrate()
        super()._handle_coordinator_update()

    @callback
    def _integrate(self) -> None:
        if not self.coordinator.last_update_success or self.coordinator.data is None:
            self._last_power = None
            self._last_time = None
            return
        now = dt_util.utcnow()
        power = float(self.entity_description.power_fn(self.coordinator.data))
        if self._last_power is not None and self._last_time is not None:
            seconds = (now - self._last_time).total_seconds()
            if 0 < seconds <= MAX_INTEGRATION_GAP:
                wh = (self._last_power + power) / 2 * seconds / 3600
                self._energy += Decimal(str(wh)) / 1000
        self._last_power = power
        self._last_time = now
