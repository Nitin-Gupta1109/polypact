"""End-to-end ``polypact.discover.check_composition`` between two agents."""

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
from polypact.server import PolypactServer
from polypact.transport import HttpTransport

pytestmark = pytest.mark.integration


def _manifest(
    *,
    skill_id: str,
    inputs: list[IOField],
    outputs: list[IOField],
) -> SkillManifest:
    return SkillManifest(
        manifest_version="0.1",
        id=skill_id,
        name=skill_id.split("#", 1)[1],
        description="composition test fixture",
        owner=Owner(agent_id=skill_id.split("#", 1)[0]),
        version="1.0.0",
        io=IOSpec(inputs=inputs, outputs=outputs),
        transfer_modes=TransferModes(
            delegate=DelegateMode(supported=True),
            lease=LeaseMode(supported=False),
            teach=TeachMode(supported=False),
            compose=ComposeMode(supported=True, compose_modes=["sequential", "parallel"]),
        ),
    )


async def _client_for(server: PolypactServer) -> PolypactClient:
    transport = httpx.ASGITransport(app=server.app())
    http_client = httpx.AsyncClient(transport=transport, base_url=server.base_url)
    return PolypactClient(
        my_agent_id="did:web:companyA.com",
        transport=HttpTransport(client=http_client),
    )


async def test_check_composition_returns_compatible_for_chained_skills() -> None:
    step1 = _manifest(
        skill_id="did:web:b.com#step1",
        inputs=[IOField(name="src", media_type="text/plain")],
        outputs=[IOField(name="mid", media_type="application/json", schema_ref="schema:M")],
    )
    step2 = _manifest(
        skill_id="did:web:b.com#step2",
        inputs=[IOField(name="mid", media_type="application/json", schema_ref="schema:M")],
        outputs=[IOField(name="out", media_type="application/json")],
    )
    server = PolypactServer(
        agent_id="did:web:b.com",
        agent_name="Pipeline Agent",
        agent_description="Composable skills.",
        base_url="http://pipeline.test",
        manifests=[step1, step2],
    )
    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://pipeline.test")
        report = await client.check_composition(card, [step1.id, step2.id], "sequential")
        assert report.compatible
        assert report.mode == "sequential"
        assert len(report.matches) == 1
        assert report.matches[0].output_field == "mid"
        assert report.matches[0].input_field == "mid"


async def test_check_composition_returns_incompatible_for_mismatched_skills() -> None:
    step1 = _manifest(
        skill_id="did:web:b.com#a",
        inputs=[IOField(name="src", media_type="text/plain")],
        outputs=[IOField(name="r", media_type="application/json", schema_ref="schema:X")],
    )
    step2 = _manifest(
        skill_id="did:web:b.com#b",
        inputs=[IOField(name="r", media_type="application/json", schema_ref="schema:Y")],
        outputs=[IOField(name="out", media_type="application/json")],
    )
    server = PolypactServer(
        agent_id="did:web:b.com",
        agent_name="Pipeline Agent",
        agent_description="Mismatched skills.",
        base_url="http://pipeline.test",
        manifests=[step1, step2],
    )
    async with await _client_for(server) as client:
        card = await client.fetch_agent_card("http://pipeline.test")
        report = await client.check_composition(card, [step1.id, step2.id], "sequential")
        assert not report.compatible
        assert report.reasons
