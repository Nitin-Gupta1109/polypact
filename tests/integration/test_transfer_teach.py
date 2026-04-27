"""End-to-end teach (PROTOCOL_SPEC.md §6.3): artifact transfer."""

from __future__ import annotations

import httpx
import pytest

from polypact.client import PolypactClient
from polypact.manifest import (
    ComposeMode,
    DelegateMode,
    IOField,
    IOSpec,
    LeaseMode,
    Owner,
    SkillManifest,
    TeachMode,
    TransferModes,
)
from polypact.negotiation import ProposedTerms
from polypact.server import PolypactServer
from polypact.transfer import TeachArtifact
from polypact.transport import HttpTransport

pytestmark = pytest.mark.integration


def _teach_manifest() -> SkillManifest:
    return SkillManifest(
        manifest_version="0.1",
        id="did:web:companyB.com#research-template",
        name="Research Prompt Template",
        description="Pre-flight prompt template for literature reviews.",
        owner=Owner(agent_id="did:web:companyB.com"),
        version="1.0.0",
        io=IOSpec(
            inputs=[IOField(name="topic", media_type="text/plain")],
            outputs=[IOField(name="report", media_type="application/json")],
        ),
        transfer_modes=TransferModes(
            delegate=DelegateMode(supported=False),
            lease=LeaseMode(supported=False),
            teach=TeachMode(supported=True),
            compose=ComposeMode(supported=False),
        ),
    )


async def test_teach_returns_registered_artifact() -> None:
    manifest = _teach_manifest()
    server = PolypactServer(
        agent_id="did:web:companyB.com",
        agent_name="CompanyB",
        agent_description="Teach provider.",
        base_url="http://companyb.test",
        manifests=[manifest],
    )
    server.register_teach_artifact(
        manifest.id,
        TeachArtifact(
            artifact_type="prompt_template",
            artifact={
                "template": "Summarize the literature on {topic} in 5 bullets.",
                "input_variables": ["topic"],
            },
            license={"use": "internal", "redistribution": False},
        ),
    )

    transport = httpx.ASGITransport(app=server.app())
    http_client = httpx.AsyncClient(transport=transport, base_url=server.base_url)
    async with PolypactClient(
        my_agent_id="did:web:companyA.com",
        transport=HttpTransport(client=http_client),
    ) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        proposal = await client.propose(
            card,
            skill_id=manifest.id,
            transfer_mode="teach",
            proposed_terms=ProposedTerms(),
        )
        agreement = await client.accept(card, negotiation_id=proposal.negotiation_id)
        result = await client.transfer_teach(card, agreement=agreement)
        assert result.artifact_type == "prompt_template"
        assert result.artifact["template"].startswith("Summarize the literature")
        assert result.license == {"use": "internal", "redistribution": False}
