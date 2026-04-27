"""End-to-end delegate (PROTOCOL_SPEC.md §6.1): Agent A calls a skill on Agent B."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from polypact.client import PolypactClient, RemoteError
from polypact.errors import UnknownSkillError
from polypact.manifest import SkillManifest
from polypact.server import PolypactServer
from polypact.transport import HttpTransport

pytestmark = pytest.mark.integration


def _build_agent_b(sample_manifest: SkillManifest) -> PolypactServer:
    server = PolypactServer(
        agent_id="did:web:companyB.com",
        agent_name="CompanyB Document Agent",
        agent_description="Serves invoice extraction.",
        base_url="http://companyb.test",
        manifests=[sample_manifest],
    )

    @server.skill(sample_manifest.id)
    async def _extract_invoice(payload: dict[str, Any]) -> dict[str, Any]:
        # Trivial fake: echo the input under a 'fields' key with a confidence score.
        return {
            "fields": {"document_id": payload.get("document_id", "unknown")},
            "confidence": 0.95,
        }

    return server


async def _client_for(server: PolypactServer) -> PolypactClient:
    transport = httpx.ASGITransport(app=server.app())
    http_client = httpx.AsyncClient(transport=transport, base_url="http://companyb.test")
    return PolypactClient(
        my_agent_id="did:web:companyA.com",
        transport=HttpTransport(client=http_client),
    )


async def test_agent_a_invokes_skill_on_agent_b(sample_manifest: SkillManifest) -> None:
    server = _build_agent_b(sample_manifest)
    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        output = await client.invoke_skill(
            card,
            sample_manifest.id,
            {"document_id": "INV-2026-001"},
        )
        assert output["fields"]["document_id"] == "INV-2026-001"
        assert output["confidence"] == 0.95


async def test_invoking_unknown_skill_raises_unknown_skill(
    sample_manifest: SkillManifest,
) -> None:
    server = _build_agent_b(sample_manifest)
    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        with pytest.raises(UnknownSkillError):
            await client.invoke_skill(card, "did:web:companyB.com#nope", {})


async def test_invoking_skill_without_handler_raises_unknown_skill(
    sample_manifest: SkillManifest,
) -> None:
    # Server publishes a manifest but registers no handler for it.
    server = PolypactServer(
        agent_id="did:web:companyB.com",
        agent_name="CompanyB",
        agent_description="No handler registered.",
        base_url="http://companyb.test",
        manifests=[sample_manifest],
    )
    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        with pytest.raises(UnknownSkillError):
            await client.invoke_skill(card, sample_manifest.id, {})


async def test_handler_exception_returns_remote_error(sample_manifest: SkillManifest) -> None:
    server = PolypactServer(
        agent_id="did:web:companyB.com",
        agent_name="CompanyB",
        agent_description="Handler raises.",
        base_url="http://companyb.test",
        manifests=[sample_manifest],
    )

    @server.skill(sample_manifest.id)
    async def _broken(_: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("kaboom")

    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        with pytest.raises(RemoteError):
            await client.invoke_skill(card, sample_manifest.id, {})
