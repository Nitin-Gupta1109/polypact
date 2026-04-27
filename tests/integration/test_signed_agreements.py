"""End-to-end signed agreements: provider signs on accept; initiator verifies."""

from __future__ import annotations

import httpx
import pytest

from polypact.client import PolypactClient
from polypact.errors import AuthorizationFailedError
from polypact.identity import AgentKeypair, DidResolver
from polypact.manifest import Pricing, SkillManifest
from polypact.negotiation import LeaseTerms, ProposedTerms
from polypact.server import PolypactServer
from polypact.transport import HttpTransport

pytestmark = pytest.mark.integration


def _build_signed_server(sample_manifest: SkillManifest) -> tuple[PolypactServer, AgentKeypair]:
    keypair = AgentKeypair.generate(did="did:web:companyB.com")
    server = PolypactServer(
        agent_id="did:web:companyB.com",
        agent_name="CompanyB",
        agent_description="Signed provider.",
        base_url="http://companyb.test",
        manifests=[sample_manifest],
        signing_key=keypair,
    )
    return server, keypair


async def test_provider_signs_agreement_and_initiator_verifies(
    sample_manifest: SkillManifest,
) -> None:
    server, _keypair = _build_signed_server(sample_manifest)

    transport = httpx.ASGITransport(app=server.app())
    http_client = httpx.AsyncClient(transport=transport, base_url=server.base_url)
    async with PolypactClient(
        my_agent_id="did:web:companyA.com",
        transport=HttpTransport(client=http_client),
    ) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        proposal = await client.propose(
            card,
            skill_id=sample_manifest.id,
            transfer_mode="lease",
            proposed_terms=ProposedTerms(
                pricing=Pricing(model="per_invocation", amount=0.04, currency="USD"),
                lease=LeaseTerms(max_invocations=10, ttl_seconds=3600),
            ),
        )
        agreement = await client.accept(card, negotiation_id=proposal.negotiation_id)

        # The agreement should carry exactly one signature: provider's.
        assert "did:web:companyB.com" in agreement.signatures
        assert agreement.signatures["did:web:companyB.com"].count(".") == 2

        # Verify against the provider's published DID document via the same
        # ASGI transport — proves end-to-end resolution + signature flow.
        resolver = DidResolver(http_client=http_client)
        await client.verify_agreement(agreement, resolver=resolver)


async def test_tampered_agreement_fails_verification(
    sample_manifest: SkillManifest,
) -> None:
    server, _keypair = _build_signed_server(sample_manifest)

    transport = httpx.ASGITransport(app=server.app())
    http_client = httpx.AsyncClient(transport=transport, base_url=server.base_url)
    async with PolypactClient(
        my_agent_id="did:web:companyA.com",
        transport=HttpTransport(client=http_client),
    ) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        proposal = await client.propose(
            card,
            skill_id=sample_manifest.id,
            transfer_mode="lease",
            proposed_terms=ProposedTerms(
                lease=LeaseTerms(max_invocations=5, ttl_seconds=3600),
            ),
        )
        agreement = await client.accept(card, negotiation_id=proposal.negotiation_id)

        # Tamper: swap the skill_id while keeping the original signature.
        forged = agreement.model_copy(update={"skill_id": "did:web:evil.com#steal"})

        resolver = DidResolver(http_client=http_client)
        with pytest.raises(AuthorizationFailedError, match="does not match"):
            await client.verify_agreement(forged, resolver=resolver)
