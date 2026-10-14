"""Tests for the web interface client and its sensors."""

import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.varta_pulse_neo.const import CONF_UNIT_ID, DOMAIN
from custom_components.varta_pulse_neo.web import (
    VartaWebAuthError,
    VartaWebClient,
    VartaWebError,
    VartaWebLockedError,
)
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er


def _client(fake_web, password: str = "secret") -> VartaWebClient:
    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
    return VartaWebClient(session, fake_web.url, "user1", password)


async def test_login_and_session_expiry(fake_web) -> None:
    client = _client(fake_web)
    data = await client.get_data()
    assert data["procImg"]["soh_pct"] == 95
    assert fake_web.logins == 1

    await client.get_data()
    assert fake_web.logins == 1  # session cookie reused

    fake_web.sessions.clear()  # session expired on the device
    await client.get_data()
    assert fake_web.logins == 2

    # device answers with something that is not the process image
    original, fake_web.data = fake_web.data, {"error": "login"}
    with pytest.raises(VartaWebError):
        await client.get_data()
    fake_web.data = original
    await client.get_data()
    assert fake_web.logins == 3
    await client.logout()
    assert "s3" not in fake_web.sessions  # current session logged out
    await client._session.close()


async def test_wrong_password_and_locked(fake_web) -> None:
    client = _client(fake_web, password="wrong")
    with pytest.raises(VartaWebAuthError):
        await client.get_data()
    fake_web.locked = True
    with pytest.raises(VartaWebLockedError):
        await client.get_data()
    await client._session.close()


def _entry(fake_varta, password: str = "secret") -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="VARTA pulse neo",
        unique_id="PN123456",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: fake_varta.port,
            CONF_UNIT_ID: 255,
            CONF_USERNAME: "user1",
            CONF_PASSWORD: password,
        },
    )


async def test_web_sensors(hass: HomeAssistant, fake_varta, fake_web) -> None:
    entry = _entry(fake_varta)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    def state(entity_id: str) -> str:
        return hass.states.get(entity_id).state

    try:
        assert state("sensor.varta_pulse_neo_state_of_health") == "95"
        assert float(state("sensor.varta_pulse_neo_usable_capacity")) == 5.868
        assert state("sensor.varta_pulse_neo_charge_cycles") == "264"
        assert (
            float(state("sensor.varta_pulse_neo_battery_charged_device_counter"))
            == 1621.656
        )
        assert float(state("sensor.varta_pulse_neo_grid_export_device_counter")) == (
            5057.88
        )
        assert float(state("sensor.varta_pulse_neo_battery_efficiency_dc")) == 95.11
        assert float(state("sensor.varta_pulse_neo_overall_efficiency_ac")) == 81.81
        assert float(state("sensor.varta_pulse_neo_battery_temperature")) == 33.1
        assert state("sensor.varta_pulse_neo_cell_voltage_spread") == "30"
        assert float(state("sensor.varta_pulse_neo_grid_current_l1")) == 5.06
        assert float(state("sensor.varta_pulse_neo_grid_frequency")) == 50.05
        assert state("binary_sensor.varta_pulse_neo_backup_mode") == "off"

        # web interface down -> only web sensors unavailable
        await fake_web.stop()
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert state("sensor.varta_pulse_neo_state_of_health") == "unavailable"
        assert state("sensor.varta_pulse_neo_state_of_charge") == "57"
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_no_web_entities_without_password(
    hass: HomeAssistant, fake_varta
) -> None:
    entry = _entry(fake_varta, password="")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert registry.async_get("sensor.varta_pulse_neo_state_of_health") is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_wrong_password_starts_reauth(
    hass: HomeAssistant, fake_varta, fake_web
) -> None:
    entry = _entry(fake_varta, password="wrong")
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert fake_web.logins == 1  # no retries that could lock the account

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH

    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], {CONF_USERNAME: "user1", CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data[CONF_PASSWORD] == "secret"
    assert entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_config_flow_invalid_auth(
    hass: HomeAssistant, fake_varta, fake_web
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    user_input = {
        CONF_HOST: "127.0.0.1",
        CONF_PORT: fake_varta.port,
        CONF_UNIT_ID: 255,
        CONF_USERNAME: "user1",
        CONF_PASSWORD: "wrong",
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**user_input, CONF_PASSWORD: "secret"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(result["result"].entry_id)
