"""Sensor platform for the VARTA pulse neo."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactivePower,
    UnitOfTemperature,
    UnitOfTime,
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


@dataclass(frozen=True, kw_only=True)
class VartaWebSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor fed by the web interface (``/cgi/data``)."""

    value_fn: Callable[[dict[str, Any]], float | int | None]


def _proc(web: dict[str, Any], key: str) -> Any:
    return web["procImg"][key]


def _counter_kwh(key: str) -> Callable[[dict[str, Any]], float]:
    return lambda web: round(web["procImg"]["counters"][key] / 3_600_000, 3)


def _ratio(numerator: str, denominator: str) -> Callable[[dict[str, Any]], float]:
    def value(web: dict[str, Any]) -> float:
        counters = web["procImg"]["counters"]
        return round(counters[numerator] / counters[denominator] * 100, 2)

    return value


def _web_energy(key: str, counter: str) -> VartaWebSensorEntityDescription:
    return VartaWebSensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        value_fn=_counter_kwh(counter),
    )


def _web_temperature(
    key: str, fn: Callable[[dict[str, Any]], float], enabled: bool = True
) -> VartaWebSensorEntityDescription:
    return VartaWebSensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=enabled,
        value_fn=fn,
    )


def _phase_current(phase: int) -> VartaWebSensorEntityDescription:
    return VartaWebSensorEntityDescription(
        key=f"grid_current_l{phase}",
        translation_key=f"grid_current_l{phase}",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda web: web["emeterAct"][f"iL{phase}ActiveGrid_cA"] / 100,
    )


def _cell_spread(web: dict[str, Any]) -> int:
    bm = web["bmAct"]
    return bm["maxCellVoltage_mV"] - bm["minCellVoltage_mV"]


WEB_SENSORS: tuple[VartaWebSensorEntityDescription, ...] = (
    # Energy counters of the device (Ws)
    _web_energy("web_battery_charged_energy", "energyCounterBattIn_Ws"),
    _web_energy("web_battery_discharged_energy", "energyCounterBattOut_Ws"),
    _web_energy("web_ac_in_energy", "energyCounterAcIn_Ws"),
    _web_energy("web_ac_out_energy", "energyCounterAcOut_Ws"),
    _web_energy("web_grid_import_energy", "energyCounterHouseIn_Ws"),
    _web_energy("web_grid_export_energy", "energyCounterHouseOut_Ws"),
    VartaWebSensorEntityDescription(
        key="web_efficiency_battery",
        translation_key="web_efficiency_battery",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_ratio("energyCounterBattOut_Ws", "energyCounterBattIn_Ws"),
    ),
    VartaWebSensorEntityDescription(
        key="web_efficiency_ac",
        translation_key="web_efficiency_ac",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_ratio("energyCounterAcOut_Ws", "energyCounterAcIn_Ws"),
    ),
    # Battery
    VartaWebSensorEntityDescription(
        key="state_of_health",
        translation_key="state_of_health",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda web: _proc(web, "soh_pct"),
    ),
    VartaWebSensorEntityDescription(
        key="usable_capacity",
        translation_key="usable_capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda web: round(_proc(web, "energyCapacity_Wh")),
    ),
    VartaWebSensorEntityDescription(
        key="charge_cycles",
        translation_key="charge_cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda web: _proc(web, "cycles"),
    ),
    VartaWebSensorEntityDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda web: web["bmAct"]["batteryVoltage_cV"] / 100,
    ),
    VartaWebSensorEntityDescription(
        key="cell_voltage_spread",
        translation_key="cell_voltage_spread",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_cell_spread,
    ),
    VartaWebSensorEntityDescription(
        key="cell_voltage_min",
        translation_key="cell_voltage_min",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda web: web["bmAct"]["minCellVoltage_mV"],
    ),
    VartaWebSensorEntityDescription(
        key="cell_voltage_max",
        translation_key="cell_voltage_max",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda web: web["bmAct"]["maxCellVoltage_mV"],
    ),
    _web_temperature(
        "battery_temperature", lambda web: web["bmAct"]["batteryTemp_dC"] / 10
    ),
    _web_temperature("inverter_temperature", lambda web: web["invAct"]["tempIgbtHb_C"]),
    _web_temperature("ambient_temperature", lambda web: web["invAct"]["tempAmbient_C"]),
    _web_temperature(
        "dcdc_temperature", lambda web: web["dcdcAct"]["tempElectronic_C"], False
    ),
    _web_temperature("ems_temperature", lambda web: web["tempEms_dC"] / 10, False),
    # Grid
    VartaWebSensorEntityDescription(
        key="grid_voltage",
        translation_key="grid_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda web: _proc(web, "gridVoltage_V"),
    ),
    VartaWebSensorEntityDescription(
        key="grid_frequency",
        translation_key="grid_frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda web: _proc(web, "gridFrequency_Hz"),
    ),
    _phase_current(1),
    _phase_current(2),
    _phase_current(3),
    VartaWebSensorEntityDescription(
        key="grid_reactive_power",
        translation_key="grid_reactive_power",
        device_class=SensorDeviceClass.REACTIVE_POWER,
        native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda web: _proc(web, "gridReactivePower_W"),
    ),
    # Limits and statistics
    VartaWebSensorEntityDescription(
        key="max_charge_power",
        translation_key="max_charge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda web: _proc(web, "maxChargePower_W"),
    ),
    VartaWebSensorEntityDescription(
        key="max_discharge_power",
        translation_key="max_discharge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda web: _proc(web, "maxDischargePower_W"),
    ),
    VartaWebSensorEntityDescription(
        key="fan_speed",
        translation_key="fan_speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda web: web["invAct"]["fanSpd_dPct"] / 10,
    ),
    VartaWebSensorEntityDescription(
        key="operating_time",
        translation_key="operating_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda web: round(
            web["procImg"]["counters"]["countActiveMinutes_m"] / 60, 1
        ),
    ),
    VartaWebSensorEntityDescription(
        key="system_starts",
        translation_key="system_starts",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda web: web["procImg"]["counters"]["countNrOfSysStarts"],
    ),
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
    if coordinator.web is not None:
        entities.extend(
            VartaWebSensor(coordinator, description) for description in WEB_SENSORS
        )
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


class VartaWebSensor(VartaEntity, SensorEntity):
    """A sensor reading a value from the web interface."""

    entity_description: VartaWebSensorEntityDescription

    @property
    def native_value(self) -> float | int | None:
        """Return the sensor value."""
        if (web := self.coordinator.web_data) is None:
            return None
        try:
            return self.entity_description.value_fn(web)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None

    @property
    def available(self) -> bool:
        """Unavailable while the web interface does not deliver the value."""
        return super().available and self.native_value is not None
