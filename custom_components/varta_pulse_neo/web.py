"""Client for the (password protected) web interface of the VARTA pulse neo.

The web interface serves the full process image of the storage system as JSON
under ``/cgi/data``. It contains values that are not available via Modbus,
e.g. real energy counters, state of health, temperatures and cell voltages.

Login: ``POST /cgi/login`` (multipart form with ``username`` and ``password``)
sets a session cookie. ``401``/``403`` means wrong credentials, ``423`` means
the account is locked after too many failed attempts.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from http import HTTPStatus
import json
from typing import Any

import aiohttp

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import CONF_WEB_HTTPS, DEFAULT_WEB_USERNAME

DEFAULT_TIMEOUT = 15


class VartaWebError(Exception):
    """Web interface not reachable or unexpected answer."""


class VartaWebAuthError(VartaWebError):
    """Credentials rejected."""


class VartaWebLockedError(VartaWebAuthError):
    """Account locked after too many failed login attempts."""


class VartaWebClient:
    """Reads ``/cgi/data`` from the web interface."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._logged_in = False
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        """Log out and release the HTTP session."""
        await self.logout()
        # Sessions from async_create_clientsession share Home Assistant's
        # connector and must be detached instead of closed.
        self._session.detach()

    async def _request(
        self, method: str, path: str, data: aiohttp.FormData | None = None
    ) -> tuple[int, str]:
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                data=data,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
            ) as resp:
                return resp.status, await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise VartaWebError(f"Web interface not reachable: {err!r}") from err

    async def login(self) -> None:
        """Log in and keep the session cookie."""
        form = aiohttp.FormData()
        form.add_field("username", self._username)
        form.add_field("password", self._password)
        status, _ = await self._request("POST", "/cgi/login", form)
        if status == HTTPStatus.LOCKED:
            raise VartaWebLockedError("Web interface account is locked")
        if status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            raise VartaWebAuthError("Invalid username or password")
        if status != HTTPStatus.OK:
            raise VartaWebError(f"Unexpected login response {status}")
        self._logged_in = True

    async def logout(self) -> None:
        """End the session (best effort)."""
        if not self._logged_in:
            return
        self._logged_in = False
        try:
            await self._request("GET", "/cgi/logout")
        except VartaWebError:
            pass

    async def get_data(self) -> dict[str, Any]:
        """Return the process image of the pulse (``data["pulse"]``).

        Logs in on demand and once more if the session has expired. A rejected
        login is raised immediately and never retried, so the account does not
        get locked.
        """
        async with self._lock:
            if not self._logged_in:
                await self.login()
            status, body = await self._request("GET", "/cgi/data")
            if status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                self._logged_in = False
                await self.login()
                status, body = await self._request("GET", "/cgi/data")
            if status != HTTPStatus.OK:
                raise VartaWebError(f"Unexpected response {status} for /cgi/data")
        try:
            payload = json.loads(body)
        except ValueError:
            payload = None
        pulse = payload.get("pulse") if isinstance(payload, dict) else None
        if not isinstance(pulse, dict) or "procImg" not in pulse:
            # E.g. a login page instead of data: log in again next time.
            self._logged_in = False
            raise VartaWebError("No pulse data in /cgi/data")
        return pulse


def create_web_client(hass: HomeAssistant, data: Mapping[str, Any]) -> VartaWebClient:
    """Create a client with its own cookie jar (the device is addressed by IP)."""
    session = async_create_clientsession(
        hass,
        verify_ssl=False,
        auto_cleanup=False,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )
    return VartaWebClient(
        session,
        web_base_url(data),
        data.get(CONF_USERNAME) or DEFAULT_WEB_USERNAME,
        data[CONF_PASSWORD],
    )


def web_base_url(data: Mapping[str, Any]) -> str:
    """Base URL of the web interface."""
    scheme = "https" if data.get(CONF_WEB_HTTPS) else "http"
    return f"{scheme}://{data[CONF_HOST]}"
