"""Polypact case study 02: Research Assistant (teach scenario).

Two agents:

* **ResearchSpecialist** — owns a curated literature-review prompt template
  she has spent years tuning. She's willing to *teach* it under restrictive
  license terms; she won't run it for anyone (no delegate, no lease).
* **GeneralistOrchestrator** — needs to brief his team on a new topic. He
  proposes a teach agreement, accepts, receives the artifact, and then runs
  it locally without further provider involvement.

The artifact transferred is a real prompt template — the kind of thing an
LLM-backed agent would slot into its own prompt cache. We don't actually call
an LLM; the value the protocol delivers is the *transfer* itself.
"""

from __future__ import annotations

import asyncio
from textwrap import indent

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
from polypact.negotiation import ProposedTerms
from polypact.server import PolypactServer
from polypact.transfer import TeachArtifact
from polypact.transport import HttpTransport

PROVIDER_DID = "did:web:research.example.org"
PROVIDER_URL = "http://research.test"
SKILL_ID = f"{PROVIDER_DID}#literature-review-template"
INITIATOR_DID = "did:web:generalist.example.com"

PROMPT_TEMPLATE = """\
You are a research analyst writing a literature review on {topic}.

Your output MUST be JSON of the form:
  {{
    "claim_summary": "<single-sentence framing of the consensus position>",
    "primary_sources": ["<url1>", "<url2>", ...],   // 3-7 entries
    "open_questions": ["<q1>", "<q2>", ...],         // 2-5 entries
    "confidence": <float in [0, 1]>
  }}

Rules:
  - Cite only peer-reviewed work or pre-prints from arXiv/SSRN/NBER.
  - Prefer sources from the last 5 years unless older work is foundational.
  - If consensus is contested, state both sides in claim_summary.
  - Do not hedge; give the strongest defensible reading.
"""


def build_template_manifest() -> SkillManifest:
    return SkillManifest(
        manifest_version="0.1",
        id=SKILL_ID,
        name="Literature Review Prompt",
        description="A curated prompt template that yields structured literature reviews.",
        owner=Owner(agent_id=PROVIDER_DID, display_name="ResearchSpecialist"),
        version="2.1.0",
        io=IOSpec(
            inputs=[IOField(name="topic", media_type="text/plain")],
            outputs=[
                IOField(
                    name="report",
                    media_type="application/json",
                    schema_ref="https://schemas.example.org/lit-review.json",
                ),
            ],
        ),
        transfer_modes=TransferModes(
            delegate=DelegateMode(supported=False),
            lease=LeaseMode(supported=False),
            teach=TeachMode(supported=True),
            compose=ComposeMode(supported=False),
        ),
    )


def build_provider() -> PolypactServer:
    keypair = AgentKeypair.generate(did=PROVIDER_DID)
    server = PolypactServer(
        agent_id=PROVIDER_DID,
        agent_name="ResearchSpecialist",
        agent_description="Specialist in literature-review prompt design.",
        base_url=PROVIDER_URL,
        manifests=[build_template_manifest()],
        signing_key=keypair,
    )
    server.register_teach_artifact(
        SKILL_ID,
        TeachArtifact(
            artifact_type="prompt_template",
            artifact={
                "template": PROMPT_TEMPLATE,
                "input_variables": ["topic"],
                "model_recommendation": "any frontier instruct model; tested on Sonnet/4-class.",
            },
            license={
                "use": "internal_only",
                "redistribution": False,
                "modify": True,
                "expires": "agreement_validity",
                "attribution_required": True,
            },
        ),
    )
    return server


async def main() -> None:
    print("=" * 72)
    print("Polypact case study 02 — Research Assistant (TEACH)")
    print("=" * 72)

    server = build_provider()
    transport = httpx.ASGITransport(app=server.app())
    http_client = httpx.AsyncClient(transport=transport, base_url=PROVIDER_URL)

    async with PolypactClient(
        my_agent_id=INITIATOR_DID,
        transport=HttpTransport(client=http_client),
    ) as client:
        # --- Discovery ---
        print("\n[Step 1] Discovery")
        card = await client.fetch_agent_card(PROVIDER_URL)
        manifests = await client.list_manifests(card)
        manifest = manifests[0]
        print(f"  Agent:        {card.name}")
        print(f"  Skill:        {manifest.id}")
        print(f"  Modes:        {card.polypact.supported_transfer_modes}")
        print("  (no delegate/lease offered — provider only teaches)")

        # --- Negotiation ---
        print("\n[Step 2] Negotiate a teach agreement")
        proposal = await client.propose(
            card,
            skill_id=SKILL_ID,
            transfer_mode="teach",
            proposed_terms=ProposedTerms(),
            rationale="Briefing the team on a new topic next sprint.",
        )
        agreement = await client.accept(card, negotiation_id=proposal.negotiation_id)
        print(f"  AGREED:       agreement_id={agreement.agreement_id}")
        print(f"  signed by:    {list(agreement.signatures.keys())}")

        # --- Verify signature ---
        print("\n[Step 3] Verify agreement signature via did:web")
        resolver = DidResolver(http_client=http_client)
        await client.verify_agreement(agreement, resolver=resolver)
        print("  signature: VERIFIED")

        # --- Teach: receive the artifact ---
        print("\n[Step 4] Receive teach artifact")
        result = await client.transfer_teach(card, agreement=agreement)
        print(f"  artifact_type: {result.artifact_type}")
        print(f"  license:       {result.license}")
        print("  template (excerpt):")
        excerpt = "\n".join(result.artifact["template"].splitlines()[:6])
        print(indent(excerpt + "\n  ...", "    "))
        print(f"  input_variables: {result.artifact['input_variables']}")

        # --- Local execution (illustrative) ---
        print("\n[Step 5] Generalist runs the template locally")
        rendered = result.artifact["template"].format(topic="LLM agent federation")
        print("  topic:    'LLM agent federation'")
        print(f"  rendered prompt: {len(rendered)} chars  (would be sent to local LLM)")
        print("  (LLM call elided in demo; protocol value is the transfer.)")

        print("\n" + "-" * 72)
        print(
            "  Provider's expertise transferred under license; no per-call "
            "billing or further provider involvement.",
        )
        print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
