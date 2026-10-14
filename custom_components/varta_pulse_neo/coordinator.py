"""Data update coordinator for the VARTA pulse neo."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import VartaClient, VartaData, VartaDeviceInfo, VartaError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type VartaConfigEntry = ConfigEntry[VartaCoordinator]

STORAGE_VERSION = 1
SAVE_DELAY = 60  # seconds

# Do not bridge gaps longer than this (e.g. device offline) with a straight line.
MAX_INTEGRATION_GAP = 300  # seconds

# Below this amount of charged energy the efficiency is not meaningful yet.
MIN_EFFICIENCY_CHARGED_KWH = 1.0


def grid_power(data: VartaData) -> int:
    """Grid power with Home Assistant sign convention (import positive).

    The device reports feed-in as positive.
    """
    return -data.grid_power


# The device has no import/export/discharge counters, so these are integrated
# from the polled power values (trapezoidal rule) for the Energy dashboard.
ENERGY_COUNTERS: dict[str, Callable[[VartaData], float]] = {
    "battery_charged_energy": lambda d: max(d.active_power, 0),
    "battery_discharged_energy": lambda d: max(-d.active_power, 0),
    "grid_import_energy": lambda d: max(grid_power(d), 0),
    "grid_export_energy": lambda d: max(-grid_power(d), 0),
}


class VartaCoordinator(DataUpdateCoordinator[VartaData]):
    """Polls the battery via Modbus TCP and keeps the energy counters."""

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
        self.energy: dict[str, float] = dict.fromkeys(ENERGY_COUNTERS, 0.0)
        # State of charge when the counters started; needed to correct the
        # efficiency for energy that is still stored in the battery.
        self.soc_start: int | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._last_data: VartaData | None = None
        self._last_time: datetime | None = None

    async def async_load_counters(self) -> None:
        """Restore the energy counters from storage."""
        if (stored := await self._store.async_load()) is None:
            return
        for key in ENERGY_COUNTERS:
            self.energy[key] = float(stored.get("energy", {}).get(key, 0.0))
        self.soc_start = stored.get("soc_start")

    async def async_save_counters(self) -> None:
        """Write the energy counters to storage now."""
        await self._store.async_save(self._counters_to_store())

    def _counters_to_store(self) -> dict[str, Any]:
        return {"energy": dict(self.energy), "soc_start": self.soc_start}

    async def _async_update_data(self) -> VartaData:
        try:
            data = await self.client.read_data()
        except VartaError as err:
            self._last_data = None
            self._last_time = None
            raise UpdateFailed(str(err)) from err
        self._integrate(data)
        return data

    def _integrate(self, data: VartaData) -> None:
        now = dt_util.utcnow()
        if self.soc_start is None:
            self.soc_start = data.soc
        if self._last_data is not None and self._last_time is not None:
            seconds = (now - self._last_time).total_seconds()
            if 0 < seconds <= MAX_INTEGRATION_GAP:
                for key, power_fn in ENERGY_COUNTERS.items():
                    watts = (power_fn(self._last_data) + power_fn(data)) / 2
                    self.energy[key] += watts * seconds / 3_600_000
        self._last_data = data
        self._last_time = now
        self._store.async_delay_save(self._counters_to_store, SAVE_DELAY)

    @property
    def efficiency(self) -> float | None:
        """Round-trip efficiency in percent since the counters started.

        Energy that was charged but is still stored in the battery is counted
        as if it had been discharged, using the change of the state of charge.
        """
        data = self.data
        charged = self.energy["battery_charged_energy"]
        if (
            data is None
            or self.soc_start is None
            or not data.installed_capacity
            or charged < MIN_EFFICIENCY_CHARGED_KWH
        ):
            return None
        stored_kwh = (data.soc - self.soc_start) / 100 * data.installed_capacity / 1000
        discharged = self.energy["battery_discharged_energy"] + stored_kwh
        return max(0.0, min(100.0, discharged / charged * 100))
