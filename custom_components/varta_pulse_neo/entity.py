"""Base entity for the VARTA pulse neo."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import VartaCoordinator


class VartaEntity(CoordinatorEntity[VartaCoordinator]):
    """Common base for VARTA entities."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: VartaCoordinator, description: EntityDescription
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
