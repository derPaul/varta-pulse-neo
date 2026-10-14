"""Tests for the Modbus client."""

import pytest

from custom_components.varta_pulse_neo.api import (
    VartaClient,
    VartaConnectionError,
    VartaModbusError,
    decode_string,
)


async def test_read_device_info_and_data(fake_varta) -> None:
    client = VartaClient("127.0.0.1", fake_varta.port)
    info = await client.read_device_info()
    assert info.serial == "PN123456"
    assert info.software_version_ems == "EMS-1.23"
    assert info.table_version == 3

    data = await client.read_data()
    assert data.soc == 57
    assert data.active_power == 1500
    assert data.grid_power == -800
    assert data.total_charged_energy == 0x15678
    assert data.installed_capacity == 6500
    assert data.pv_sensor_power is None  # register missing -> modbus exception

    fake_varta.registers[1102] = 2300
    assert (await client.read_data()).pv_sensor_power == 2300
    await client.close()


async def test_modbus_exception(fake_varta) -> None:
    client = VartaClient("127.0.0.1", fake_varta.port)
    with pytest.raises(VartaModbusError):
        await client.read_registers(5000, 1)
    # connection still usable afterwards
    assert await client.read_registers(1068, 1) == [57]
    await client.close()


async def test_cannot_connect(socket_enabled) -> None:
    client = VartaClient("127.0.0.1", 1, timeout=1)
    with pytest.raises(VartaConnectionError):
        await client.read_registers(1068, 1)


def test_decode_string_one_char_per_register() -> None:
    assert decode_string([0x0041, 0x0042, 0x0000]) == "AB"
    assert decode_string([0x4142, 0x4300]) == "ABC"
