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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VartaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_entities([VartaProblemSensor(entry.runtime_data, PROBLEM_SENSOR)])


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
