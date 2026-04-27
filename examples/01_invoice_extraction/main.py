"""Polypact case study 01: Invoice Extraction (lease scenario).

Two agents:

* **CompanyB Document Agent** — provider; publishes ``extract-invoice`` and
  signs agreements with a fresh Ed25519 keypair.
* **CompanyA Finance Agent** — initiator; proposes a 50-invocation lease,
  accepts, runs the batch, and confirms the budget is enforced when the
  lease is exhausted.

The whole flow runs in-process via ``httpx.ASGITransport``; no real network
binding is required to reproduce the example.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from polypact.client import PolypactClient
from polypact.errors import AgreementViolatedError
from polypact.identity import AgentKeypair, DidResolver
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
from polypact.negotiation import LeaseTerms, ProposedTerms
from polypact.server import PolypactServer
from polypact.transport import HttpTransport

PROVIDER_DID = "did:web:companyB.com"
PROVIDER_URL = "http://companyb.test"
SKILL_ID = f"{PROVIDER_DID}#extract-invoice"
INITIATOR_DID = "did:web:companyA.com"

BATCH = [
    {"invoice_id": f"INV-2026-{i:03d}", "vendor": "Acme Corp", "subtotal": 100 + i}
    for i in range(1, 51)
]


def build_invoice_manifest() -> SkillManifest:
    return SkillManifest(
        manifest_version="0.1",
        id=SKILL_ID,
        name="Invoice Field Extraction",
        description="Extract structured fields from invoice PDFs.",
        owner=Owner(agent_id=PROVIDER_DID, display_name="CompanyB Document Agent"),
        version="1.2.0",
        io=IOSpec(
            inputs=[
                IOField(
                    name="document",
                    media_type="application/json",
                    schema_ref="https://schemas.example.com/invoice-input.json",
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
            compose=ComposeMode(supported=False),
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


def build_provider() -> PolypactServer:
    keypair = AgentKeypair.generate(did=PROVIDER_DID)
    server = PolypactServer(
        agent_id=PROVIDER_DID,
        agent_name="CompanyB Document Agent",
        agent_description="Extracts invoice fields under negotiated terms.",
        base_url=PROVIDER_URL,
        manifests=[build_invoice_manifest()],
        signing_key=keypair,
    )

    @server.skill(SKILL_ID)
    async def extract(payload: dict[str, Any]) -> dict[str, Any]:
        # Stand-in for real PDF extraction: synthesize confident structured fields.
        return {
            "fields": {
                "invoice_id": payload.get("invoice_id"),
                "vendor": payload.get("vendor"),
                "subtotal": payload.get("subtotal"),
                "currency": "USD",
            },
            "confidence": 0.95,
        }

    return server


async def main() -> None:
    print("=" * 72)
    print("Polypact case study 01 — Invoice Extraction (LEASE)")
    print("=" * 72)

    server = build_provider()
    transport = httpx.ASGITransport(app=server.app())
    http_client = httpx.AsyncClient(transport=transport, base_url=PROVIDER_URL)

    async with PolypactClient(
        my_agent_id=INITIATOR_DID,
        transport=HttpTransport(client=http_client),
    ) as client:
        # --- Step 1: Discovery ---
        print("\n[Step 1] Discovery")
        card = await client.fetch_agent_card(PROVIDER_URL)
        manifests = await client.list_manifests(card)
        invoice = manifests[0]
        print(f"  Agent:         {card.name} ({card.url})")
        print(f"  Skill:         {invoice.id}")
        print(f"  Modes offered: {card.polypact.supported_transfer_modes}")
        published = invoice.terms.pricing
        assert published is not None
        print(f"  Provider list: ${published.amount}/invocation {published.currency}")

        # --- Step 2: Negotiation ---
        print("\n[Step 2] Negotiate a 50-invocation lease (counter to $0.04)")
        proposal = await client.propose(
            card,
            skill_id=SKILL_ID,
            transfer_mode="lease",
            proposed_terms=ProposedTerms(
                pricing=Pricing(model="per_invocation", amount=0.04, currency="USD"),
                lease=LeaseTerms(max_invocations=50, ttl_seconds=3600),
            ),
            rationale="Q3 close batch — 50 invoices.",
        )
        print(f"  proposed:    state={proposal.state} (id={proposal.negotiation_id})")
        agreement = await client.accept(card, negotiation_id=proposal.negotiation_id)
        print(f"  AGREED:      agreement_id={agreement.agreement_id}")
        print(f"  valid until: {agreement.valid_until.isoformat()}")
        terms_lease = agreement.terms.lease
        terms_pricing = agreement.terms.pricing
        assert terms_lease is not None
        assert terms_pricing is not None
        print(f"  bound terms: max_invocations={terms_lease.max_invocations}, ")
        print(f"               price=${terms_pricing.amount}/invocation")
        print(f"  signed by:   {list(agreement.signatures.keys())}")

        # --- Step 3: Verify the provider's signature against their DID document ---
        print("\n[Step 3] Verify agreement signature via did:web")
        resolver = DidResolver(http_client=http_client)
        await client.verify_agreement(agreement, resolver=resolver)
        print(f"  resolved:  {PROVIDER_DID}/.well-known/did.json (cached)")
        print("  signature: VERIFIED (Ed25519 over canonical JSON)")

        # --- Step 4: Run the lease ---
        print(f"\n[Step 4] Process {len(BATCH)} invoices under the lease")
        for i, doc in enumerate(BATCH, start=1):
            output = await client.invoke_with_agreement(
                card,
                agreement=agreement,
                payload=doc,
            )
            if i in (1, 2, len(BATCH) - 1, len(BATCH)) or i % 25 == 0:
                state = server.lease.state_for(agreement.agreement_id)
                used = state.invocations_used if state else "?"
                cap = state.max_invocations if state else "?"
                print(
                    f"  [#{i:02d}] {doc['invoice_id']:>14} → "
                    f"subtotal={output['fields']['subtotal']:>3}  "
                    f"({used}/{cap} used)",
                )
            elif i == 3:
                print("  ...")

        # --- Step 5: Lease enforcement ---
        print("\n[Step 5] Confirm lease enforcement")
        try:
            await client.invoke_with_agreement(
                card,
                agreement=agreement,
                payload=BATCH[0],
            )
        except AgreementViolatedError as exc:
            print(f"  invoke #51:  REJECTED ({exc.message})")

        # --- Summary ---
        print("\n" + "-" * 72)
        final = server.lease.state_for(agreement.agreement_id)
        assert final is not None
        cost = final.invocations_used * (terms_pricing.amount or 0.0)
        print(
            f"  Total invocations: {final.invocations_used}/{final.max_invocations}  "
            f"|  Cost: ${cost:.2f} {terms_pricing.currency}",
        )
        print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
