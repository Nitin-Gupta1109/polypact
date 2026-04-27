"""End-to-end compose (PROTOCOL_SPEC.md §6.4): success and -32004 mismatch."""

from __future__ import annotations

import httpx
import pytest

from polypact.client import PolypactClient
from polypact.errors import CapabilityMismatchError
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
from polypact.negotiation import ComposeTerms, ProposedTerms
from polypact.server import PolypactServer
from polypact.transport import HttpTransport

pytestmark = pytest.mark.integration


def _step(*, skill_id: str, inputs: list[IOField], outputs: list[IOField]) -> SkillManifest:
    return SkillManifest(
        manifest_version="0.1",
        id=skill_id,
        name=skill_id.split("#", 1)[1],
        description="step manifest",
        owner=Owner(agent_id=skill_id.split("#", 1)[0]),
        version="1.0.0",
        io=IOSpec(inputs=inputs, outputs=outputs),
        transfer_modes=TransferModes(
            delegate=DelegateMode(supported=True),
            lease=LeaseMode(supported=False),
            teach=TeachMode(supported=False),
            compose=ComposeMode(supported=True, compose_modes=["sequential"]),
        ),
    )


async def _client_for(server: PolypactServer) -> PolypactClient:
    transport = httpx.ASGITransport(app=server.app())
    http_client = httpx.AsyncClient(transport=transport, base_url=server.base_url)
    return PolypactClient(
        my_agent_id="did:web:companyA.com",
        transport=HttpTransport(client=http_client),
    )


async def test_compose_synthesizes_composite_manifest() -> None:
    step1 = _step(
        skill_id="did:web:companyB.com#step1",
        inputs=[IOField(name="src", media_type="text/plain")],
        outputs=[IOField(name="mid", media_type="application/json", schema_ref="schema:M")],
    )
    step2 = _step(
        skill_id="did:web:companyB.com#step2",
        inputs=[IOField(name="mid", media_type="application/json", schema_ref="schema:M")],
        outputs=[IOField(name="final", media_type="application/json")],
    )
    server = PolypactServer(
        agent_id="did:web:companyB.com",
        agent_name="CompanyB",
        agent_description="Pipeline.",
        base_url="http://companyb.test",
        manifests=[step1, step2],
    )

    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        proposal = await client.propose(
            card,
            skill_id=step1.id,  # leading skill stands in as the "anchor"
            transfer_mode="compose",
            proposed_terms=ProposedTerms(
                compose=ComposeTerms(
                    compose_kind="sequential",
                    steps=[step1.id, step2.id],
                ),
            ),
        )
        agreement = await client.accept(card, negotiation_id=proposal.negotiation_id)
        composite = await client.transfer_compose(card, agreement=agreement)
        assert composite.id.startswith("did:web:companyB.com#composite-")
        assert composite.io.inputs[0].name == "src"
        assert composite.io.outputs[0].name == "final"


async def test_compose_with_mismatched_io_returns_capability_mismatch() -> None:
    step1 = _step(
        skill_id="did:web:companyB.com#a",
        inputs=[IOField(name="src", media_type="text/plain")],
        outputs=[IOField(name="r", media_type="application/json", schema_ref="schema:X")],
    )
    step2 = _step(
        skill_id="did:web:companyB.com#b",
        inputs=[IOField(name="r", media_type="application/json", schema_ref="schema:Y")],
        outputs=[IOField(name="final", media_type="application/json")],
    )
    server = PolypactServer(
        agent_id="did:web:companyB.com",
        agent_name="CompanyB",
        agent_description="Mismatched pipeline.",
        base_url="http://companyb.test",
        manifests=[step1, step2],
    )

    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://companyb.test")
        proposal = await client.propose(
            card,
            skill_id=step1.id,
            transfer_mode="compose",
            proposed_terms=ProposedTerms(
                compose=ComposeTerms(
                    compose_kind="sequential",
                    steps=[step1.id, step2.id],
                ),
            ),
        )
        agreement = await client.accept(card, negotiation_id=proposal.negotiation_id)
        with pytest.raises(CapabilityMismatchError):
            await client.transfer_compose(card, agreement=agreement)
