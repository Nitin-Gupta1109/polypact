"""Polypact case study 03: Logistics Pipeline (compose scenario).

Four agents, three of them specialists:

* **routing.example.com** — ``optimize-route`` (shipments → ordered stops)
* **inventory.example.com** — ``check-stock`` (ordered stops → stock-checked stops)
* **eta.example.com** — ``compute-eta`` (stock-checked stops → stops with ETAs)

…and one orchestrator:

* **fulfill.example.com** — *FulfillmentOrchestrator*. Maintains mirrored copies
  of the three specialist manifests, offers compose mode, and synthesizes a
  composite skill manifest from any agreed pipeline.

A client (**ShipperClient**) discovers all three specialists, then negotiates
a compose agreement with the orchestrator referencing the three skills as a
sequential pipeline. The orchestrator's compose primitive type-checks the
composition (§3.3) and emits one composite manifest the client can treat as
a single skill.

Note on Phase 4 scope: compose looks up step manifests from the *orchestrator's*
local registry. The "three agents" framing is preserved by mirroring manifests
into the orchestrator at startup. Cross-agent compose (where the orchestrator
fetches manifests from foreign agents at compose time) is future work.
"""

from __future__ import annotations

import asyncio

import httpx

from polypact.client import PolypactClient
from polypact.identity import AgentKeypair, DidResolver
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

ROUTING_DID = "did:web:routing.example.com"
INVENTORY_DID = "did:web:inventory.example.com"
ETA_DID = "did:web:eta.example.com"
ORCH_DID = "did:web:fulfill.example.com"
CLIENT_DID = "did:web:shipper.example.com"

ROUTING_URL = "http://routing.test"
INVENTORY_URL = "http://inventory.test"
ETA_URL = "http://eta.test"
ORCH_URL = "http://fulfill.test"

ROUTING_SKILL = f"{ROUTING_DID}#optimize-route"
INVENTORY_SKILL = f"{INVENTORY_DID}#check-stock"
ETA_SKILL = f"{ETA_DID}#compute-eta"


def _step_manifest(
    *,
    skill_id: str,
    name: str,
    description: str,
    inputs: list[IOField],
    outputs: list[IOField],
) -> SkillManifest:
    did = skill_id.split("#", 1)[0]
    return SkillManifest(
        manifest_version="0.1",
        id=skill_id,
        name=name,
        description=description,
        owner=Owner(agent_id=did),
        version="1.0.0",
        io=IOSpec(inputs=inputs, outputs=outputs),
        transfer_modes=TransferModes(
            delegate=DelegateMode(supported=True),
            lease=LeaseMode(supported=False),
            teach=TeachMode(supported=False),
            compose=ComposeMode(supported=True, compose_modes=["sequential"]),
        ),
    )


def routing_manifest() -> SkillManifest:
    return _step_manifest(
        skill_id=ROUTING_SKILL,
        name="Route Optimizer",
        description="Order shipments by lowest-distance route.",
        inputs=[
            IOField(
                name="shipments",
                media_type="application/json",
                schema_ref="https://schemas.example.com/shipment-list.json",
            ),
        ],
        outputs=[
            IOField(
                name="ordered_stops",
                media_type="application/json",
                schema_ref="https://schemas.example.com/stops.json",
            ),
        ],
    )


def inventory_manifest() -> SkillManifest:
    return _step_manifest(
        skill_id=INVENTORY_SKILL,
        name="Stock Checker",
        description="Annotate stops with current warehouse stock levels.",
        inputs=[
            IOField(
                name="ordered_stops",
                media_type="application/json",
                schema_ref="https://schemas.example.com/stops.json",
            ),
        ],
        outputs=[
            IOField(
                name="stock_checked_stops",
                media_type="application/json",
                schema_ref="https://schemas.example.com/stops-with-stock.json",
            ),
        ],
    )


def eta_manifest() -> SkillManifest:
    return _step_manifest(
        skill_id=ETA_SKILL,
        name="ETA Computer",
        description="Compute arrival ETAs given checked stops.",
        inputs=[
            IOField(
                name="stock_checked_stops",
                media_type="application/json",
                schema_ref="https://schemas.example.com/stops-with-stock.json",
            ),
        ],
        outputs=[
            IOField(
                name="stops_with_etas",
                media_type="application/json",
                schema_ref="https://schemas.example.com/stops-with-etas.json",
            ),
        ],
    )


def build_specialist(
    *,
    did: str,
    name: str,
    base_url: str,
    manifest: SkillManifest,
) -> PolypactServer:
    return PolypactServer(
        agent_id=did,
        agent_name=name,
        agent_description=f"Specialist agent for {manifest.name}.",
        base_url=base_url,
        manifests=[manifest],
        signing_key=AgentKeypair.generate(did=did),
    )


def build_orchestrator(specialist_manifests: list[SkillManifest]) -> PolypactServer:
    """Build the orchestrator with mirrored copies of all specialist manifests.

    Phase 4's compose primitive looks skills up locally; mirroring keeps the
    cross-agent narrative honest while leaving cross-agent skill resolution
    to a future phase.
    """
    return PolypactServer(
        agent_id=ORCH_DID,
        agent_name="FulfillmentOrchestrator",
        agent_description="Hosts compose mode for fulfillment pipelines.",
        base_url=ORCH_URL,
        manifests=specialist_manifests,
        signing_key=AgentKeypair.generate(did=ORCH_DID),
    )


async def main() -> None:
    print("=" * 72)
    print("Polypact case study 03 — Logistics Pipeline (COMPOSE)")
    print("=" * 72)

    routing_m = routing_manifest()
    inventory_m = inventory_manifest()
    eta_m = eta_manifest()

    routing_srv = build_specialist(
        did=ROUTING_DID,
        name="RoutingAgent",
        base_url=ROUTING_URL,
        manifest=routing_m,
    )
    inventory_srv = build_specialist(
        did=INVENTORY_DID,
        name="InventoryAgent",
        base_url=INVENTORY_URL,
        manifest=inventory_m,
    )
    eta_srv = build_specialist(
        did=ETA_DID,
        name="ETAAgent",
        base_url=ETA_URL,
        manifest=eta_m,
    )
    orchestrator = build_orchestrator([routing_m, inventory_m, eta_m])

    # Each agent gets its own httpx client (in-process ASGI).
    routing_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=routing_srv.app()),
        base_url=ROUTING_URL,
    )
    inventory_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=inventory_srv.app()),
        base_url=INVENTORY_URL,
    )
    eta_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=eta_srv.app()),
        base_url=ETA_URL,
    )
    orch_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=orchestrator.app()),
        base_url=ORCH_URL,
    )

    try:
        # --- Step 1: Discover the three specialists ---
        print("\n[Step 1] Discover three specialist agents")
        async with PolypactClient(
            my_agent_id=CLIENT_DID,
            transport=HttpTransport(client=routing_client),
        ) as c:
            r_card = await c.fetch_agent_card(ROUTING_URL)
            r_manifests = await c.list_manifests(r_card)
            print(f"  {r_card.name}: {r_manifests[0].id}")
        async with PolypactClient(
            my_agent_id=CLIENT_DID,
            transport=HttpTransport(client=inventory_client),
        ) as c:
            i_card = await c.fetch_agent_card(INVENTORY_URL)
            i_manifests = await c.list_manifests(i_card)
            print(f"  {i_card.name}: {i_manifests[0].id}")
        async with PolypactClient(
            my_agent_id=CLIENT_DID,
            transport=HttpTransport(client=eta_client),
        ) as c:
            e_card = await c.fetch_agent_card(ETA_URL)
            e_manifests = await c.list_manifests(e_card)
            print(f"  {e_card.name}: {e_manifests[0].id}")

        # --- Step 2: Negotiate compose with the orchestrator ---
        print("\n[Step 2] Negotiate compose with the FulfillmentOrchestrator")
        async with PolypactClient(
            my_agent_id=CLIENT_DID,
            transport=HttpTransport(client=orch_client),
        ) as c:
            orch_card = await c.fetch_agent_card(ORCH_URL)
            print(f"  orchestrator: {orch_card.name}")
            print(f"  modes:        {orch_card.polypact.supported_transfer_modes}")
            proposal = await c.propose(
                orch_card,
                skill_id=ROUTING_SKILL,  # anchor; compose terms carry the real list
                transfer_mode="compose",
                proposed_terms=ProposedTerms(
                    compose=ComposeTerms(
                        compose_kind="sequential",
                        steps=[ROUTING_SKILL, INVENTORY_SKILL, ETA_SKILL],
                    ),
                ),
                rationale="Daily fulfillment pipeline.",
            )
            agreement = await c.accept(orch_card, negotiation_id=proposal.negotiation_id)
            print(f"  AGREED:       {agreement.agreement_id}")
            print(f"  signed by:    {list(agreement.signatures.keys())}")

            # --- Step 3: Verify agreement ---
            print("\n[Step 3] Verify agreement signature via did:web")
            await c.verify_agreement(
                agreement,
                resolver=DidResolver(http_client=orch_client),
            )
            print("  signature: VERIFIED")

            # --- Step 4: Receive composite manifest ---
            print("\n[Step 4] Receive synthesized composite manifest")
            composite = await c.transfer_compose(orch_card, agreement=agreement)
            print(f"  id:        {composite.id}")
            print(f"  name:      {composite.name}")
            print(f"  inputs:    {[f.name for f in composite.io.inputs]}")
            print(f"             ({composite.io.inputs[0].schema_ref})")
            print(f"  outputs:   {[f.name for f in composite.io.outputs]}")
            print(f"             ({composite.io.outputs[0].schema_ref})")
            print(
                "  type-check: PASS — 2 sequential edges verified per §3.3",
            )

        print("\n" + "-" * 72)
        print(
            "  Three specialist skills exposed to the client as a single composite skill,",
        )
        print(
            "  type-checked at composition time. Client now sees one skill at the orchestrator,",
        )
        print(
            "  not three. (Cross-agent invocation is the next protocol layer.)",
        )
        print("=" * 72)
    finally:
        for c in (routing_client, inventory_client, eta_client, orch_client):
            await c.aclose()


if __name__ == "__main__":
    asyncio.run(main())
