#!/usr/bin/env python3
"""Shared HTTP client for Home Assistant REST API.

Consolidates the duplicated auth/header/timeout/JSON-parse code that previously
lived in `tools/reload_config.py` and `tools/ha_api_diagnostic.py`.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from tools.common import (
    DEFAULT_HA_URL,
    HARequestError,
    get_env_int,
    load_env_file,
    validate_ha_url,
)


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
        error = validate_ha_url(url)
        if error:
            raise HARequestError(error)
        if not token:
            raise HARequestError(
                "HA_TOKEN not found. Set it in .env or the environment."
            )
        self.url = url.rstrip("/")
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
        load_env_file()
        url = os.getenv("HA_URL", DEFAULT_HA_URL)
        token = os.getenv("HA_TOKEN", "")
        timeout, warning = get_env_int("HA_REQUEST_TIMEOUT", 10)
        if warning:
            # Surface as a printed warning rather than raising — a bad timeout
            # value shouldn't block API access entirely.
            print(f"\u26a0\ufe0f  {warning}")
        return cls(url, token, timeout=timeout)

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        """GET ``path`` (e.g. ``/api/states``). Raises HARequestError on failure."""
        url = f"{self.url}{path}"
        try:
            return self._session.get(
                url, headers=self.headers, timeout=self.timeout, **kwargs
            )
        except requests.RequestException as e:
            raise HARequestError(f"GET {path} failed: {e}") from e

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        """POST to ``path``. Raises HARequestError on failure."""
        url = f"{self.url}{path}"
        try:
            return self._session.post(
                url, headers=self.headers, timeout=self.timeout, **kwargs
            )
        except requests.RequestException as e:
            raise HARequestError(f"POST {path} failed: {e}") from e

    def get_json(self, path: str, **kwargs: Any) -> Any:
        """GET ``path`` and parse JSON. Returns None on non-JSON responses."""
        response = self.get(path, **kwargs)
        if response.status_code != 200:
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
