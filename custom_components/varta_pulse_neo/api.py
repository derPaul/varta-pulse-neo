"""Minimal async Modbus TCP client for the VARTA pulse neo.

The VARTA storage systems (element, pulse, pulse neo, link, flex) expose a
read-only register table via Modbus TCP (port 502, holding registers).
Only function code 0x03 (read holding registers) is needed, so a tiny
self-contained client is used instead of a pymodbus dependency.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import struct

# Register map (holding registers, big-endian words)
REG_SW_VERSION_EMS = 1000  # 17 registers, string
REG_SW_VERSION_ENS = 1017  # 17 registers, string
REG_SW_VERSION_INVERTER = 1034  # 17 registers, string
REG_TABLE_VERSION = 1051  # uint16
REG_SERIAL = 1054  # 10 registers, string
REG_NUMBER_MODULES = 1064  # uint16
REG_STATE = 1065  # uint16
REG_ACTIVE_POWER = 1066  # int16, W, positive = charging
REG_APPARENT_POWER = 1067  # int16, VA
REG_SOC = 1068  # uint16, %
REG_TOTAL_CHARGED_ENERGY = 1069  # uint32 (low word first), Wh
REG_INSTALLED_CAPACITY = 1071  # uint16, x10 Wh
REG_ERROR_CODE = 1072  # uint16
REG_GRID_POWER = 1078  # int16, W, positive = feed-in
REG_PV_SENSOR_POWER = 1102  # uint16, W (only with optional PV sensor)

DEFAULT_TIMEOUT = 5.0


class VartaError(Exception):
    """Base error."""


class VartaConnectionError(VartaError):
    """Device could not be reached or the connection broke."""


class VartaModbusError(VartaError):
    """Device answered with a Modbus exception."""


@dataclass(slots=True)
class VartaDeviceInfo:
    """Static information about the device."""

    serial: str
    software_version_ems: str
    software_version_ens: str
    software_version_inverter: str
    table_version: int


@dataclass(slots=True)
class VartaData:
    """Live values read from the device."""

    soc: int
    state: int
    active_power: int
    apparent_power: int
    grid_power: int
    total_charged_energy: int
    installed_capacity: int
    number_modules: int
    error_code: int
    pv_sensor_power: int | None


def _to_int16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def decode_string(registers: list[int]) -> str:
    """Decode a register block into a string.

    Depending on firmware the device either packs two ASCII characters per
    register or one character per register (padded with a zero byte), so all
    zero and non-printable bytes are simply dropped.
    """
    raw = b"".join(struct.pack(">H", reg) for reg in registers)
    return "".join(chr(b) for b in raw if 32 <= b < 127).strip()


class VartaClient:
    """Async client for one VARTA storage system."""

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 255,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._transaction_id = 0
        self._lock = asyncio.Lock()

    async def _connect(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (OSError, TimeoutError) as err:
            raise VartaConnectionError(
                f"Cannot connect to {self.host}:{self.port}: {err}"
            ) from err

    async def close(self) -> None:
        """Close the TCP connection."""
        writer, self._reader, self._writer = self._writer, None, None
        if writer is not None:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), self.timeout)
            except (OSError, TimeoutError):
                pass

    async def read_registers(self, address: int, count: int) -> list[int]:
        """Read holding registers, reconnecting once on a broken connection."""
        async with self._lock:
            try:
                return await self._read(address, count)
            except VartaConnectionError:
                await self.close()
                return await self._read(address, count)

    async def _read(self, address: int, count: int) -> list[int]:
        if self._writer is None or self._writer.is_closing():
            await self._connect()
        assert self._reader is not None and self._writer is not None

        self._transaction_id = (self._transaction_id + 1) & 0xFFFF
        tid = self._transaction_id
        request = struct.pack(">HHHBBHH", tid, 0, 6, self.unit_id, 0x03, address, count)
        try:
            self._writer.write(request)
            await self._writer.drain()
            while True:
                header = await asyncio.wait_for(
                    self._reader.readexactly(7), self.timeout
                )
                rtid, _proto, length, _unit = struct.unpack(">HHHB", header)
                pdu = await asyncio.wait_for(
                    self._reader.readexactly(length - 1), self.timeout
                )
                if rtid == tid:
                    break
                # Stale answer of an earlier, timed-out request: skip it.
        except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
            await self.close()
            raise VartaConnectionError(
                f"Communication with {self.host}:{self.port} failed: {err!r}"
            ) from err

        function = pdu[0]
        if function == 0x83:
            raise VartaModbusError(
                f"Modbus exception {pdu[1]} reading register {address}"
            )
        if function != 0x03 or pdu[1] != count * 2 or len(pdu) != 2 + count * 2:
            await self.close()
            raise VartaConnectionError(f"Malformed response reading register {address}")
        return list(struct.unpack(f">{count}H", pdu[2:]))

    async def read_device_info(self) -> VartaDeviceInfo:
        """Read serial number and firmware versions."""
        return VartaDeviceInfo(
            serial=decode_string(await self.read_registers(REG_SERIAL, 10)),
            software_version_ems=decode_string(
                await self.read_registers(REG_SW_VERSION_EMS, 17)
            ),
            software_version_ens=decode_string(
                await self.read_registers(REG_SW_VERSION_ENS, 17)
            ),
            software_version_inverter=decode_string(
                await self.read_registers(REG_SW_VERSION_INVERTER, 17)
            ),
            table_version=(await self.read_registers(REG_TABLE_VERSION, 1))[0],
        )

    async def read_data(self, read_pv_sensor: bool = True) -> VartaData:
        """Read all live values."""
        block = await self.read_registers(REG_NUMBER_MODULES, 9)  # 1064..1072
        grid = await self.read_registers(REG_GRID_POWER, 1)
        pv_sensor_power: int | None = None
        if read_pv_sensor:
            try:
                pv_sensor_power = (await self.read_registers(REG_PV_SENSOR_POWER, 1))[0]
            except VartaModbusError:
                pv_sensor_power = None

        def reg(address: int) -> int:
            return block[address - REG_NUMBER_MODULES]

        return VartaData(
            number_modules=reg(REG_NUMBER_MODULES),
            state=reg(REG_STATE),
            active_power=_to_int16(reg(REG_ACTIVE_POWER)),
            apparent_power=_to_int16(reg(REG_APPARENT_POWER)),
            soc=reg(REG_SOC),
            total_charged_energy=(reg(REG_TOTAL_CHARGED_ENERGY + 1) << 16)
            | reg(REG_TOTAL_CHARGED_ENERGY),
            installed_capacity=reg(REG_INSTALLED_CAPACITY) * 10,
            error_code=reg(REG_ERROR_CODE),
            grid_power=_to_int16(grid[0]),
            pv_sensor_power=pv_sensor_power,
        )
