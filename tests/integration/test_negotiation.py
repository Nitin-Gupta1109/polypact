"""End-to-end negotiation tests (PROTOCOL_SPEC.md §5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from polypact.client import PolypactClient
from polypact.errors import NegotiationStateError
from polypact.manifest import Pricing, SkillManifest
from polypact.negotiation import (
    LeaseTerms,
    NegotiationState,
    ProposedTerms,
)
from polypact.server import PolypactServer
from polypact.transport import HttpTransport

pytestmark = pytest.mark.integration


def _build_server(sample_manifest: SkillManifest) -> PolypactServer:
    return PolypactServer(
        agent_id="did:web:companyB.com",
        agent_name="CompanyB Document Agent",
        agent_description="Negotiable invoice extraction.",
        base_url="http://companyb.test",
        manifests=[sample_manifest],
    )


async def _client_for(server: PolypactServer) -> PolypactClient:
    transport = httpx.ASGITransport(app=server.app())
    http_client = httpx.AsyncClient(transport=transport, base_url=server.base_url)
    return PolypactClient(
        my_agent_id="did:web:companyA.com",
        transport=HttpTransport(client=http_client),
    )


def _initial_terms() -> ProposedTerms:
    return ProposedTerms(
        pricing=Pricing(model="per_invocation", amount=0.04, currency="USD"),
        lease=LeaseTerms(max_invocations=50, ttl_seconds=3600),
    )


def _counter_terms() -> ProposedTerms:
    return ProposedTerms(
        pricing=Pricing(model="per_invocation", amount=0.05, currency="USD"),
        lease=LeaseTerms(max_invocations=100, ttl_seconds=7200),
    )


# --- Full flow with one counter then accept ---


async def test_full_flow_with_counter_then_accept(sample_manifest: SkillManifest) -> None:
    server = _build_server(sample_manifest)
    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")

        status = await client.propose(
            card,
            skill_id=sample_manifest.id,
            transfer_mode="lease",
            proposed_terms=_initial_terms(),
            rationale="Q3 close batch",
        )
        assert status.state == NegotiationState.PROPOSED
        negotiation_id = status.negotiation_id

        countered = await client.counter_propose(
            card,
            negotiation_id=negotiation_id,
            proposed_terms=_counter_terms(),
        )
        assert countered.state == NegotiationState.PROPOSED
        # Counter resets expiry, so it should be later than the original.
        assert countered.expires_at >= status.expires_at

        agreement = await client.accept(card, negotiation_id=negotiation_id)
        assert agreement.negotiation_id == negotiation_id
        assert agreement.transfer_mode == "lease"
        assert agreement.skill_id == sample_manifest.id
        # Accepted terms are the most recent (counter) terms, not the initial offer.
        assert agreement.terms.pricing is not None
        assert agreement.terms.pricing.amount == 0.05
        assert agreement.terms.lease is not None
        assert agreement.terms.lease.max_invocations == 100
        assert agreement.signatures == {}  # Phase 3: stubbed
        assert agreement.parties.initiator == "did:web:companyA.com"
        assert agreement.parties.provider == "did:web:companyB.com"


# --- Rejection ---


async def test_rejection_terminates_negotiation(sample_manifest: SkillManifest) -> None:
    server = _build_server(sample_manifest)
    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        status = await client.propose(
            card,
            skill_id=sample_manifest.id,
            transfer_mode="lease",
            proposed_terms=_initial_terms(),
        )
        rejected = await client.reject(
            card,
            negotiation_id=status.negotiation_id,
            reason="terms too aggressive",
        )
        assert rejected.state == NegotiationState.REJECTED
        assert rejected.rejection_reason == "terms too aggressive"

        # Subsequent operations on a rejected negotiation must fail.
        with pytest.raises(NegotiationStateError):
            await client.accept(card, negotiation_id=status.negotiation_id)


# --- Expiry ---


async def test_proposed_transitions_to_expired_on_timeout(
    sample_manifest: SkillManifest,
) -> None:
    server = _build_server(sample_manifest)
    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")

        # Propose with a tiny TTL.
        status = await client.propose(
            card,
            skill_id=sample_manifest.id,
            transfer_mode="lease",
            proposed_terms=_initial_terms(),
            negotiation_ttl_seconds=1,
        )
        assert status.state == NegotiationState.PROPOSED

        # Force the wall-clock past expiry by retrieving the record with a
        # future timestamp via the coordinator. This avoids a real sleep in
        # the test (faster + deterministic) while exercising lazy expiry.
        future = datetime.now(UTC) + timedelta(seconds=10)
        refreshed = server.negotiations.get(status.negotiation_id, now=future)
        assert refreshed.state == NegotiationState.EXPIRED

        # Subsequent accept must fail with terminal-state error.
        with pytest.raises(NegotiationStateError):
            await client.accept(card, negotiation_id=status.negotiation_id)
