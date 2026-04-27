"""Phase 1 demo: Agent A discovers Agent B's skill manifests over HTTP.

Uses an in-process httpx ASGI transport so the demo runs without binding to a
real port. Same code path as a network-bound run; just no socket.
"""

from __future__ import annotations

import asyncio

import httpx

from polypact.client import PolypactClient
from polypact.manifest import (
    SLA,
    ComposeMode,
    DataHandling,
    DelegateMode,
    IOField,
    IOSpec,
    LeaseMode,
    Owner,
    Pricing,
    SkillManifest,
    TeachMode,
    Terms,
    TransferModes,
)
from polypact.server import create_app
from polypact.transport import HttpTransport


def build_sample_manifest() -> SkillManifest:
    return SkillManifest(
        manifest_version="0.1",
        id="did:web:companyB.com#extract-invoice",
        name="Invoice Field Extraction",
        description="Extract structured fields from invoice PDFs.",
        owner=Owner(
            agent_id="did:web:companyB.com",
            display_name="CompanyB Document Agent",
        ),
        version="1.2.0",
        io=IOSpec(
            inputs=[
                IOField(
                    name="document",
                    media_type="application/pdf",
                    schema_ref="https://schemas.example.com/pdf-input.json",
                ),
            ],
            outputs=[
                IOField(
                    name="fields",
                    media_type="application/json",
                    schema_ref="https://schema.org/Invoice",
                ),
            ],
        ),
        transfer_modes=TransferModes(
            delegate=DelegateMode(supported=True),
            lease=LeaseMode(supported=True, max_invocations=1000, max_ttl_seconds=86400),
            teach=TeachMode(supported=False, reason="proprietary"),
            compose=ComposeMode(supported=True, compose_modes=["sequential"]),
        ),
        terms=Terms(
            pricing=Pricing(model="per_invocation", amount=0.05, currency="USD"),
            data_handling=DataHandling(
                retention_seconds=0,
                processing_locations=["EU"],
                subprocessors_allowed=False,
            ),
            sla=SLA(p50_latency_ms=2000, p99_latency_ms=8000, availability=0.99),
        ),
    )


async def main() -> None:
    base_url = "http://companyb.test"

    agent_b = create_app(
        agent_id="did:web:companyB.com",
        agent_name="CompanyB Document Agent",
        agent_description="Hosts skills CompanyB is willing to share.",
        base_url=base_url,
        manifests=[build_sample_manifest()],
    )

    transport = httpx.ASGITransport(app=agent_b)
    http_client = httpx.AsyncClient(transport=transport, base_url=base_url)

    async with PolypactClient(
        my_agent_id="did:web:companyA.com",
        transport=HttpTransport(client=http_client),
    ) as client:
        card = await client.fetch_agent_card(base_url)
        print(f"Discovered agent: {card.name}")
        print(f"  url:                       {card.url}")
        print(f"  polypact version:          {card.polypact.version}")
        print(f"  supported transfer modes:  {card.polypact.supported_transfer_modes}")
        print(f"  supported conformance:     {card.polypact.supported_conformance_levels}")
        print()

        manifests = await client.list_manifests(card)
        print(f"Found {len(manifests)} manifest(s):")
        for manifest in manifests:
            print(f"  - {manifest.id}")
            print(f"      name:         {manifest.name}")
            print(f"      version:      {manifest.version}")
            print(f"      inputs:       {[i.name for i in manifest.io.inputs]}")
            print(f"      outputs:      {[o.name for o in manifest.io.outputs]}")
            print(f"      pricing:      {manifest.terms.pricing}")


if __name__ == "__main__":
    asyncio.run(main())
