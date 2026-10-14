"""Binary sensor platform for the VARTA pulse neo."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import BATTERY_STATES
from .coordinator import VartaConfigEntry
from .entity import VartaEntity

PARALLEL_UPDATES = 0

STATE_ERROR = 5

PROBLEM_SENSOR = BinarySensorEntityDescription(
    key="problem",
    device_class=BinarySensorDeviceClass.PROBLEM,
)

BACKUP_MODE_SENSOR = BinarySensorEntityDescription(
    key="backup_mode",
    translation_key="backup_mode",
    device_class=BinarySensorDeviceClass.RUNNING,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VartaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        VartaProblemSensor(coordinator, PROBLEM_SENSOR)
    ]
    if coordinator.web is not None:
        entities.append(VartaBackupModeSensor(coordinator, BACKUP_MODE_SENSOR))
    async_add_entities(entities)


class VartaProblemSensor(VartaEntity, BinarySensorEntity):
    """On when the battery reports an error code or the error state."""

    @property
    def is_on(self) -> bool:
        """Return true if there is a problem."""
        data = self.coordinator.data
        return data.error_code != 0 or data.state == STATE_ERROR

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the raw error code and state."""
        data = self.coordinator.data
        return {
            "error_code": data.error_code,
            "state": BATTERY_STATES.get(data.state, data.state),
        }


class VartaBackupModeSensor(VartaEntity, BinarySensorEntity):
    """On while the storage system supplies the house in backup mode."""

    @property
    def is_on(self) -> bool | None:
        """Return true in backup mode."""
        if (web := self.coordinator.web_data) is None:
            return None
        return bool(web["procImg"].get("backupMode"))

    @property
    def available(self) -> bool:
        """Unavailable while the web interface delivers no data."""
        return super().available and self.coordinator.web_data is not None
