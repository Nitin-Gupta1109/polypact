"""End-to-end lease (PROTOCOL_SPEC.md §6.2): success, exhaustion, expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from polypact.client import PolypactClient
from polypact.errors import AgreementViolatedError
from polypact.manifest import Pricing, SkillManifest
from polypact.negotiation import LeaseTerms, ProposedTerms
from polypact.server import PolypactServer
from polypact.transport import HttpTransport

pytestmark = pytest.mark.integration


def _build_server(sample_manifest: SkillManifest) -> PolypactServer:
    server = PolypactServer(
        agent_id="did:web:companyB.com",
        agent_name="CompanyB",
        agent_description="Lease provider.",
        base_url="http://companyb.test",
        manifests=[sample_manifest],
    )

    @server.skill(sample_manifest.id)
    async def _handler(payload: dict[str, Any]) -> dict[str, Any]:
        return {"echoed": payload, "n": payload.get("n", 0)}

    return server


async def _client_for(server: PolypactServer) -> PolypactClient:
    transport = httpx.ASGITransport(app=server.app())
    http_client = httpx.AsyncClient(transport=transport, base_url=server.base_url)
    return PolypactClient(
        my_agent_id="did:web:companyA.com",
        transport=HttpTransport(client=http_client),
    )


def _lease_terms(*, max_invocations: int, ttl_seconds: int) -> ProposedTerms:
    return ProposedTerms(
        pricing=Pricing(model="per_invocation", amount=0.04, currency="USD"),
        lease=LeaseTerms(max_invocations=max_invocations, ttl_seconds=ttl_seconds),
    )


async def test_lease_invocation_succeeds(sample_manifest: SkillManifest) -> None:
    server = _build_server(sample_manifest)
    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        proposal = await client.propose(
            card,
            skill_id=sample_manifest.id,
            transfer_mode="lease",
            proposed_terms=_lease_terms(max_invocations=3, ttl_seconds=3600),
        )
        agreement = await client.accept(card, negotiation_id=proposal.negotiation_id)

        output = await client.invoke_with_agreement(
            card,
            agreement=agreement,
            payload={"n": 1},
        )
        assert output["echoed"] == {"n": 1}
        # Lease state should reflect one used invocation.
        state = server.lease.state_for(agreement.agreement_id)
        assert state is not None
        assert state.invocations_used == 1
        assert state.invocations_remaining == 2


async def test_lease_exhaustion_rejects_with_agreement_violated(
    sample_manifest: SkillManifest,
) -> None:
    server = _build_server(sample_manifest)
    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        proposal = await client.propose(
            card,
            skill_id=sample_manifest.id,
            transfer_mode="lease",
            proposed_terms=_lease_terms(max_invocations=2, ttl_seconds=3600),
        )
        agreement = await client.accept(card, negotiation_id=proposal.negotiation_id)

        await client.invoke_with_agreement(card, agreement=agreement, payload={"n": 1})
        await client.invoke_with_agreement(card, agreement=agreement, payload={"n": 2})

        with pytest.raises(AgreementViolatedError, match="exhausted"):
            await client.invoke_with_agreement(card, agreement=agreement, payload={"n": 3})


async def test_lease_expiry_rejects_with_agreement_violated(
    sample_manifest: SkillManifest,
) -> None:
    server = _build_server(sample_manifest)
    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        proposal = await client.propose(
            card,
            skill_id=sample_manifest.id,
            transfer_mode="lease",
            proposed_terms=_lease_terms(max_invocations=10, ttl_seconds=1),
        )
        await client.accept(card, negotiation_id=proposal.negotiation_id)

        # Manually expire the agreement by rewriting valid_until in the store.
        record = server.negotiations.get(proposal.negotiation_id)
        assert record.agreement is not None
        expired_agreement = record.agreement.model_copy(
            update={"valid_until": datetime.now(UTC) - timedelta(seconds=1)},
        )
        server.negotiation_store.put(
            record.model_copy(update={"agreement": expired_agreement}),
        )

        with pytest.raises(AgreementViolatedError, match="expired"):
            await client.invoke_with_agreement(
                card,
                agreement=expired_agreement,
                payload={"n": 1},
            )
