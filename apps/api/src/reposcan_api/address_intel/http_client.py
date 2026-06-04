"""Minimal best-effort JSON HTTP client for address-intel providers.

Uses only the standard library (urllib) — no new dependencies, consistent with
the edge-first/local-first mandate. Every call is best-effort: any network,
timeout, HTTP, or parse error returns None so providers degrade rather than
raise. A descriptive User-Agent is sent (required by OSM/Nominatim/Overpass
fair-use policy and good manners for the Census/FCC endpoints).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Protocol

DEFAULT_USER_AGENT = "RepoScanPro-AddressIntel/1.0 (authorized repossession field tool)"
DEFAULT_TIMEOUT_S = 6.0


class JsonHttpClient(Protocol):
    def get_json(self, url: str, *, params: Optional[dict] = None, timeout: float = DEFAULT_TIMEOUT_S) -> Optional[object]:
        ...

    def post_json(self, url: str, *, data: dict, timeout: float = DEFAULT_TIMEOUT_S) -> Optional[object]:
        ...


class UrllibJsonClient:
    """Stdlib JSON client. Returns parsed JSON (dict/list) or None on any failure."""

    def __init__(self, *, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self._user_agent = user_agent

    def _request(self, request: urllib.request.Request, timeout: float) -> Optional[object]:
        request.add_header("User-Agent", self._user_agent)
        request.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (trusted gov/OSM hosts)
                raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
            return None

    def get_json(self, url: str, *, params: Optional[dict] = None, timeout: float = DEFAULT_TIMEOUT_S) -> Optional[object]:
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{query}"
        return self._request(urllib.request.Request(url, method="GET"), timeout)

    def post_json(self, url: str, *, data: dict, timeout: float = DEFAULT_TIMEOUT_S) -> Optional[object]:
        body = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(url, data=body, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        return self._request(request, timeout)
