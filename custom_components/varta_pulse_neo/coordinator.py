"""Data update coordinator for the VARTA pulse neo."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VartaClient, VartaData, VartaDeviceInfo, VartaError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type VartaConfigEntry = ConfigEntry[VartaCoordinator]


class VartaCoordinator(DataUpdateCoordinator[VartaData]):
    """Polls the battery via Modbus TCP."""

    config_entry: VartaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VartaConfigEntry,
        client: VartaClient,
        device_info: VartaDeviceInfo,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.device_info = device_info

    async def _async_update_data(self) -> VartaData:
        try:
            return await self.client.read_data()
        except VartaError as err:
            raise UpdateFailed(str(err)) from err
