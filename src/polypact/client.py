"""Polypact client SDK.

In Phase 1, :class:`PolypactClient` covers Level-1 discovery: fetching an
Agent Card and listing/fetching manifests. Negotiation, invocation, and
transfer methods land in later phases.
"""

from __future__ import annotations

from types import TracebackType
from typing import Self
from urllib.parse import quote

import httpx

from polypact.discovery import AgentCard
from polypact.manifest import SkillManifest
from polypact.transport import HttpTransport


class PolypactClient:
    """High-level client for talking to a Polypact-compliant agent.

    Owns an :class:`HttpTransport` unless one is injected. Use as an async
    context manager to ensure the underlying HTTP client is closed.
    """

    def __init__(
        self,
        *,
        my_agent_id: str,
        transport: HttpTransport | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.my_agent_id = my_agent_id
        if transport is not None and http_client is not None:
            msg = "pass either transport or http_client, not both"
            raise ValueError(msg)
        if transport is not None:
            self._transport = transport
            self._owns_transport = False
        else:
            self._transport = HttpTransport(client=http_client)
            self._owns_transport = True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_transport:
            await self._transport.aclose()

    async def aclose(self) -> None:
        """Close the underlying transport if this client owns it."""
        if self._owns_transport:
            await self._transport.aclose()

    async def fetch_agent_card(self, base_url: str) -> AgentCard:
        """Fetch and parse the Agent Card from ``{base_url}/.well-known/agent.json``."""
        url = f"{base_url.rstrip('/')}/.well-known/agent.json"
        body = await self._transport.get_json(url)
        return AgentCard.model_validate(body)

    async def list_manifests(self, card: AgentCard) -> list[SkillManifest]:
        """Fetch all skill manifests from the agent described by ``card``."""
        body = await self._transport.get_json(card.polypact.manifests_url)
        manifests = body.get("manifests", [])
        return [SkillManifest.model_validate(m) for m in manifests]

    async def fetch_manifest(self, card: AgentCard, skill_id: str) -> SkillManifest:
        """Fetch a single manifest by skill ID from the agent described by ``card``.

        The skill ID is URL-encoded; DID-style IDs contain ``#`` which would
        otherwise be parsed as a URL fragment and never reach the server.
        """
        encoded = quote(skill_id, safe="")
        url = f"{card.polypact.manifests_url}/{encoded}"
        body = await self._transport.get_json(url)
        return SkillManifest.model_validate(body)
