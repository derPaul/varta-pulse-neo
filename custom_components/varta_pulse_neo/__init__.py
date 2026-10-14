"""The VARTA pulse neo integration."""

from __future__ import annotations

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from .api import VartaClient, VartaError
from .const import CONF_UNIT_ID, DEFAULT_SCAN_INTERVAL, DEFAULT_UNIT_ID, DOMAIN
from .coordinator import STORAGE_VERSION, VartaConfigEntry, VartaCoordinator
from .web import create_web_client

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: VartaConfigEntry) -> bool:
    """Set up VARTA pulse neo from a config entry."""
    client = VartaClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID),
    )
    try:
        device_info = await client.read_device_info()
    except VartaError as err:
        await client.close()
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = VartaCoordinator(
        hass,
        entry,
        client,
        device_info,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        create_web_client(hass, entry.data) if entry.data.get(CONF_PASSWORD) else None,
    )
    await coordinator.async_load_counters()
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await _async_close_clients(coordinator)
        raise

    entry.runtime_data = coordinator

    async def _async_close(_event: Event) -> None:
        await _async_close_clients(coordinator)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_close)
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VartaConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_save_counters()
        await _async_close_clients(entry.runtime_data)
    return unload_ok


async def _async_close_clients(coordinator: VartaCoordinator) -> None:
    await coordinator.client.close()
    if coordinator.web is not None:
        await coordinator.web.close()


async def async_remove_entry(hass: HomeAssistant, entry: VartaConfigEntry) -> None:
    """Delete the stored energy counters when the entry is removed."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_update_listener(hass: HomeAssistant, entry: VartaConfigEntry) -> None:
    """Reload when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)
