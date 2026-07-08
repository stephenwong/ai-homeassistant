"""Shared HTTP client for Home Assistant REST API.

Consolidates the duplicated auth/header/timeout/JSON-parse code that previously
lived in `tools/reload_config.py` and `tools/ha_api_diagnostic.py`.
"""

import asyncio
import os
import sys
from typing import Any

import aiohttp
import requests

from tools.common import (
    DEFAULT_HA_URL,
    HARequestError,
    get_env_int,
    load_env_file,
    validate_ha_url,
)


def _validate_connection(url: str, token: str) -> str:
    """Validate URL format and token presence; return stripped URL."""
    error = validate_ha_url(url)
    if error:
        raise HARequestError(error)
    if not token:
        raise HARequestError("HA_TOKEN not found. Set it in .env or the environment.")
    return url.rstrip("/")


def _env_config() -> tuple[str, str, int]:
    """Load .env once; return (url, token, timeout) from env or defaults."""
    load_env_file()
    url = os.getenv("HA_URL", DEFAULT_HA_URL)
    token = os.getenv("HA_TOKEN", "")
    timeout, warning = get_env_int("HA_REQUEST_TIMEOUT", 10)
    if warning:
        print(f"\u26a0\ufe0f  {warning}", file=sys.stderr)
    return url, token, timeout


class HAClient:
    """Thin wrapper around the Home Assistant REST API."""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        timeout: int = 10,
        session: requests.Session | None = None,
    ):
        """Initialize the client.

        Args:
            url: Base HA URL (e.g. ``http://homeassistant.local:8123``).
            token: Long-lived access token.
            timeout: Per-request timeout in seconds.
            session: Optional pre-configured requests.Session for testing.
        """
        self.url = _validate_connection(url, token)
        self.token = token
        self.timeout = timeout
        self._session = session or requests.Session()

    @property
    def headers(self) -> dict[str, str]:
        """Auth + content-type headers for every request."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @classmethod
    def from_env(cls) -> HAClient:
        """Construct a client from HA_URL/HA_TOKEN/HA_REQUEST_TIMEOUT.

        Loads ``.env`` exactly once via :func:`load_env_file` so that callers
        don't need to remember to do it. ``load_env_file`` is idempotent — it
        only sets env vars that are present in the file, so calling it again
        later is safe.
        """
        url, token, timeout = _env_config()
        return cls(url, token, timeout=timeout)

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Dispatch a request to ``path``. Raises HARequestError on failure."""
        url = f"{self.url}{path}"
        try:
            return getattr(self._session, method.lower())(
                url, headers=self.headers, timeout=self.timeout, **kwargs
            )
        except requests.RequestException as e:
            raise HARequestError(f"{method.upper()} {path} failed: {e}") from e

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        """GET ``path`` (e.g. ``/api/states``). Raises HARequestError on failure."""
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        """POST to ``path``. Raises HARequestError on failure."""
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> requests.Response:
        """PUT to ``path``. Raises HARequestError on failure."""
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        """DELETE ``path``. Raises HARequestError on failure."""
        return self._request("DELETE", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> requests.Response:
        """PATCH ``path``. Raises HARequestError on failure."""
        return self._request("PATCH", path, **kwargs)

    def get_json(self, path: str, **kwargs: Any) -> Any:
        """GET ``path`` and parse JSON. Returns None on non-JSON responses."""
        response = self.get(path, **kwargs)
        if response.status_code < 200 or response.status_code >= 300:
            raise HARequestError(
                f"GET {path} returned HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as e:
            raise HARequestError(f"GET {path} returned non-JSON response: {e}") from e

    def call_service(
        self,
        domain: str,
        service: str,
        data: dict | None = None,
    ) -> bool:
        """Call ``<domain>/<service>`` (e.g. ``automation``, ``reload``).

        Returns ``True`` if HA responded with HTTP 200.
        """
        path = f"/api/services/{domain}/{service}"
        response = self.post(path, json=data or {})
        return response.status_code == 200


class HAWSClient:
    """Thin WebSocket client for HA commands not available via REST.

    HA removed /api/error_log and /api/automation/trace from the REST API.
    These are now WebSocket-only (system_log/list, trace/list, trace/get).
    """

    def __init__(
        self,
        url: str,
        token: str,
        *,
        timeout: int = 10,
        session_factory=None,
    ):
        self.url = _validate_connection(url, token)
        self.token = token
        self.timeout = timeout
        self._session_factory = session_factory
        self._msg_id = 0

    @classmethod
    def from_env(cls) -> HAWSClient:
        """Construct a client from HA_URL/HA_TOKEN/HA_REQUEST_TIMEOUT."""
        url, token, timeout = _env_config()
        return cls(url, token, timeout=timeout)

    @property
    def _ws_url(self) -> str:
        """Convert http URL to WebSocket URL (ws:// or wss://)."""
        url = self.url
        if url.lower().startswith("https://"):
            return "wss://" + url[8:]
        return "ws://" + url[7:]

    def command(self, command_type: str, **params: Any) -> Any:
        """Send a WebSocket command synchronously, return the result.

        Raises HARequestError on connection failure, auth failure, or
        command failure.
        """
        self._msg_id = 0
        return asyncio.run(self._command(command_type, **params))

    async def _command(self, command_type: str, **params: Any) -> Any:
        session_factory = self._session_factory or aiohttp.ClientSession
        ws_timeout = aiohttp.ClientWSTimeout(
            ws_receive=self.timeout, ws_close=self.timeout
        )
        try:
            async with (
                session_factory() as session,
                session.ws_connect(
                    f"{self._ws_url}/api/websocket",
                    timeout=ws_timeout,
                ) as ws,
            ):
                await self._authenticate(ws)
                return await self._send_and_receive(ws, command_type, **params)
        except (OSError, aiohttp.ClientError) as e:
            raise HARequestError(
                f"cannot connect to HA WebSocket at {self._ws_url}: {e}"
            ) from e

    async def _authenticate(self, ws) -> None:
        """Perform the WebSocket auth handshake."""
        msg = await ws.receive_json()
        if msg.get("type") != "auth_required":
            raise HARequestError(
                f"unexpected WebSocket message: expected auth_required, "
                f"got {msg.get('type')}"
            )
        await ws.send_json({"type": "auth", "access_token": self.token})
        msg = await ws.receive_json()
        if msg.get("type") == "auth_invalid":
            raise HARequestError(
                f"authentication failed \u2014 check HA_TOKEN: "
                f"{msg.get('message', 'invalid token')}"
            )
        if msg.get("type") != "auth_ok":
            raise HARequestError(
                f"unexpected WebSocket message: expected auth_ok, got {msg.get('type')}"
            )

    async def _send_and_receive(self, ws, command_type: str, **params: Any) -> Any:
        """Send a command and loop until we receive the matching result."""
        self._msg_id += 1
        sent_id = self._msg_id
        await ws.send_json({"id": sent_id, "type": command_type, **params})

        # Loop until we get our result, skipping event/pong/other messages.
        for _ in range(100):
            msg = await ws.receive_json()
            if msg.get("type") == "result" and msg.get("id") == sent_id:
                if not msg.get("success", False):
                    error = msg.get("error", {})
                    raise HARequestError(
                        f"{command_type} failed: "
                        f"{error.get('message', 'unknown error')}"
                    )
                return msg.get("result")

        raise HARequestError(f"{command_type} timed out waiting for result")
