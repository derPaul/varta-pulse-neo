"""Fixtures: a fake VARTA Modbus TCP server."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import struct
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest


def _encode_string(text: str, count: int) -> list[int]:
    raw = text.encode().ljust(count * 2, b"\0")
    return list(struct.unpack(f">{count}H", raw))


def default_registers() -> dict[int, int]:
    regs: dict[int, int] = {}

    def put(address: int, values: list[int]) -> None:
        for i, value in enumerate(values):
            regs[address + i] = value

    put(1000, _encode_string("EMS-1.23", 17))
    put(1017, _encode_string("ENS-4.56", 17))
    put(1034, _encode_string("INV-7.89", 17))
    put(1051, [3])
    put(1054, _encode_string("PN123456", 10))
    put(1064, [1])  # modules
    put(1065, [2])  # charging
    put(1066, [1500])  # active power
    put(1067, [1520])  # apparent power
    put(1068, [57])  # soc
    put(1069, [0x5678, 0x0001])  # total charged energy 0x15678 Wh = 87672
    put(1071, [650])  # capacity -> 6500 Wh
    put(1072, [0])  # error
    put(1078, [(-800) & 0xFFFF])  # 800 W import (device: feed-in positive)
    return regs


class FakeVarta:
    """Serves holding registers like the VARTA storage."""

    def __init__(self) -> None:
        self.registers = default_registers()
        self.server: asyncio.Server | None = None
        self.port = 0
        self._writers: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server is None:
            return
        server, self.server = self.server, None
        server.close()
        for writer in list(self._writers):
            writer.transport.abort()
        await server.wait_closed()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writers.add(writer)
        try:
            while True:
                header = await reader.readexactly(7)
                tid, _proto, length, unit = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)
                _fc, address, count = struct.unpack(">BHH", pdu)
                if all(address + i in self.registers for i in range(count)):
                    values = [self.registers[address + i] for i in range(count)]
                    body = struct.pack(f">BB{count}H", 3, count * 2, *values)
                else:
                    body = struct.pack(">BB", 0x83, 2)  # illegal data address
                writer.write(struct.pack(">HHHB", tid, 0, len(body) + 1, unit) + body)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()


@pytest.fixture
async def fake_varta(socket_enabled):
    server = FakeVarta()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    yield


class FakeVartaWeb:
    """Serves the login and /cgi/data like the VARTA web interface."""

    def __init__(self) -> None:
        self.username = "user1"
        self.password = "secret"
        self.locked = False
        self.logins = 0
        self.sessions: set[str] = set()
        self.data = json.loads(
            (Path(__file__).parent / "fixtures/cgi_data.json").read_text()
        )
        self.server: TestServer | None = None

    @property
    def url(self) -> str:
        assert self.server is not None
        return str(self.server.make_url("/"))

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/cgi/login", self._login)
        app.router.add_get("/cgi/data", self._data)
        app.router.add_get("/cgi/logout", self._logout)
        self.server = TestServer(app, host="127.0.0.1")
        await self.server.start_server()

    async def stop(self) -> None:
        if self.server is not None:
            await self.server.close()

    async def _login(self, request: web.Request) -> web.Response:
        self.logins += 1
        if self.locked:
            return web.Response(status=423)
        form = await request.post()
        if (
            form.get("username") != self.username
            or form.get("password") != self.password
        ):
            return web.Response(status=401)
        session_id = f"s{self.logins}"
        self.sessions.add(session_id)
        response = web.Response(status=200)
        response.set_cookie("beaker.session.id", session_id)
        return response

    async def _data(self, request: web.Request) -> web.Response:
        if request.cookies.get("beaker.session.id") not in self.sessions:
            return web.Response(status=403)
        return web.json_response(self.data)

    async def _logout(self, request: web.Request) -> web.Response:
        self.sessions.discard(request.cookies.get("beaker.session.id", ""))
        return web.Response(status=200)


@pytest.fixture
async def fake_web(socket_enabled):
    server = FakeVartaWeb()
    await server.start()
    with patch(
        "custom_components.varta_pulse_neo.web.web_base_url",
        return_value=server.url,
    ):
        yield server
    await server.stop()
