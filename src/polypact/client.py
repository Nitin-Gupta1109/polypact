"""Polypact client SDK.

Phase 1 covered Level-1 discovery (Agent Card + manifest list/fetch).
Phase 2 adds Level-2 calls: ``invoke_skill`` (delegate-mode invocation) and
``check_composition``.
"""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

import httpx

from polypact.discovery import AgentCard
from polypact.errors import PolypactError, UnknownSkillError
from polypact.manifest import CompatibilityReport, ComposeKind, SkillManifest
from polypact.transport import HttpTransport
from polypact.transport.errors import INTERNAL_ERROR

_RPC_PATH = "/polypact/v1/rpc"


class RemoteError(PolypactError):
    """Raised when a remote agent returns a JSON-RPC error envelope."""


_KNOWN_DOMAIN_CODES: dict[int, type[PolypactError]] = {
    UnknownSkillError.code: UnknownSkillError,
}


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

    async def invoke_skill(
        self,
        card: AgentCard,
        skill_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Invoke a delegate-mode skill on the agent described by ``card``.

        Phase 2 ships ``skill_id``-keyed invocation; Phase 3 will add an
        ``agreement_id``-keyed form gated by negotiated terms.
        """
        params = {
            "agent_id": self.my_agent_id,
            "trace_id": str(uuid.uuid4()),
            "skill_id": skill_id,
            "input": payload,
        }
        result = await self._call(card, "polypact.task.invoke", params)
        output: dict[str, Any] = result["output"]
        return output

    async def check_composition(
        self,
        card: AgentCard,
        skill_ids: list[str],
        mode: ComposeKind,
    ) -> CompatibilityReport:
        """Ask the remote agent to type-check a composition of its skills."""
        params = {
            "agent_id": self.my_agent_id,
            "trace_id": str(uuid.uuid4()),
            "skill_ids": skill_ids,
            "mode": mode,
        }
        result = await self._call(card, "polypact.discover.check_composition", params)
        return CompatibilityReport.model_validate(result)

    async def _call(
        self,
        card: AgentCard,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        rpc_url = f"{card.url.rstrip('/')}{_RPC_PATH}"
        envelope = await self._transport.call(rpc_url, method, params)
        if "error" in envelope:
            err = envelope["error"]
            code = err.get("code", INTERNAL_ERROR)
            message = err.get("message", "remote error")
            data = err.get("data")
            exc_cls = _KNOWN_DOMAIN_CODES.get(code, RemoteError)
            raise exc_cls(message, data=data)
        result: dict[str, Any] = envelope["result"]
        return result
