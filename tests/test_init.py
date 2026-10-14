"""Tests for setup, config flow and sensors."""

from datetime import timedelta
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.varta_pulse_neo.const import CONF_UNIT_ID, DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util


async def test_config_flow(hass: HomeAssistant, fake_varta) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_UNIT_ID: 255},
    )
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: fake_varta.port, CONF_UNIT_ID: 255},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "PN123456"
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(result["result"].entry_id)


async def test_sensors(hass: HomeAssistant, fake_varta) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="VARTA pulse neo",
        unique_id="PN123456",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: fake_varta.port, CONF_UNIT_ID: 255},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    try:

        def state(entity_id: str) -> str:
            return hass.states.get(entity_id).state

        assert state("sensor.varta_pulse_neo_state_of_charge") == "57"
        assert state("sensor.varta_pulse_neo_battery_power") == "1500"
        assert state("sensor.varta_pulse_neo_charge_power") == "1500"
        assert state("sensor.varta_pulse_neo_discharge_power") == "0"
        assert state("sensor.varta_pulse_neo_grid_power") == "800"
        assert state("sensor.varta_pulse_neo_grid_import_power") == "800"
        assert state("sensor.varta_pulse_neo_grid_export_power") == "0"
        assert state("sensor.varta_pulse_neo_state") == "charge"
        assert float(state("sensor.varta_pulse_neo_total_charged_energy")) == 87.672
        assert float(state("sensor.varta_pulse_neo_battery_energy_charged")) == 0

        # 1500 W for 36 s -> 15 Wh
        later = dt_util.utcnow() + timedelta(seconds=36)
        with patch(
            "custom_components.varta_pulse_neo.sensor.dt_util.utcnow",
            return_value=later,
        ):
            await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert float(state("sensor.varta_pulse_neo_battery_energy_charged")) == 0.015
        assert float(state("sensor.varta_pulse_neo_grid_import_energy")) == 0.008

        # device goes away -> unavailable
        await fake_varta.stop()
        await entry.runtime_data.client.close()
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert state("sensor.varta_pulse_neo_state_of_charge") == "unavailable"

    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_options_flow(hass: HomeAssistant, fake_varta) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="PN123456",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: fake_varta.port, CONF_UNIT_ID: 255},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.update_interval == timedelta(seconds=30)
    assert await hass.config_entries.async_unload(entry.entry_id)
