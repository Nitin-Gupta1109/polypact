"""End-to-end discovery: Agent A fetches Agent B's Agent Card and manifests."""

from __future__ import annotations

import httpx
import pytest

from polypact.client import PolypactClient
from polypact.manifest import SkillManifest
from polypact.server import create_app
from polypact.transport import HttpTransport

pytestmark = pytest.mark.integration


@pytest.fixture
def agent_b_app(sample_manifest: SkillManifest) -> object:
    return create_app(
        agent_id="did:web:companyB.com",
        agent_name="CompanyB Document Agent",
        agent_description="Serves invoice extraction.",
        base_url="http://companyb.test",
        manifests=[sample_manifest],
    )


async def _client_for(app: object) -> PolypactClient:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    http_client = httpx.AsyncClient(transport=transport, base_url="http://companyb.test")
    return PolypactClient(
        my_agent_id="did:web:companyA.com",
        transport=HttpTransport(client=http_client),
    )


async def test_agent_a_fetches_agent_b_card(
    agent_b_app: object,
    sample_manifest: SkillManifest,
) -> None:
    async with await _client_for(agent_b_app) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        assert card.name == "CompanyB Document Agent"
        assert card.polypact.version == "0.1"
        assert "delegate" in card.polypact.supported_transfer_modes
        assert card.polypact.manifests_url == "http://companyb.test/polypact/v1/manifests"


async def test_agent_a_lists_agent_b_manifests(
    agent_b_app: object,
    sample_manifest: SkillManifest,
) -> None:
    async with await _client_for(agent_b_app) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        manifests = await client.list_manifests(card)
        assert len(manifests) == 1
        assert manifests[0].id == sample_manifest.id
        assert manifests[0] == sample_manifest


async def test_agent_a_fetches_specific_manifest(
    agent_b_app: object,
    sample_manifest: SkillManifest,
) -> None:
    async with await _client_for(agent_b_app) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        manifest = await client.fetch_manifest(card, sample_manifest.id)
        assert manifest == sample_manifest


async def test_unknown_skill_returns_404(
    agent_b_app: object,
) -> None:
    async with await _client_for(agent_b_app) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.fetch_manifest(card, "did:web:companyB.com#nope")
        assert exc_info.value.response.status_code == 404
