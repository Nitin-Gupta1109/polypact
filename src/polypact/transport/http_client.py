"""Async HTTP client wrapper around :mod:`httpx` for Polypact transport.

Covers the GET endpoints (Agent Card, manifest list/fetch) needed by Phase 1
discovery, plus a generic JSON-RPC ``call`` for future phases. Higher-level
SDK code lives in :mod:`polypact.client`.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import httpx

from polypact.transport.jsonrpc import JsonRpcId


class HttpTransport:
    """Thin wrapper that owns an :class:`httpx.AsyncClient`.

    Pass an explicit ``client`` to share connection pools or to inject an
    in-process ASGI transport for tests.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this transport owns it."""
        if self._owns_client:
            await self._client.aclose()

    async def get_json(self, url: str) -> Any:
        """GET ``url`` and return the parsed JSON body. Raises on non-2xx."""
        response = await self._client.get(url)
        response.raise_for_status()
        return response.json()

    async def call(
        self,
        rpc_url: str,
        method: str,
        params: dict[str, Any],
        *,
        request_id: JsonRpcId = 1,
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and return the raw response envelope."""
        body = {"jsonrpc": "2.0", "method": method, "params": params, "id": request_id}
        response = await self._client.post(rpc_url, json=body)
        response.raise_for_status()
        envelope: dict[str, Any] = response.json()
        return envelope
