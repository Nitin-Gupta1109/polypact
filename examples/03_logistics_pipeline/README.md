# Example 03 — Logistics Pipeline (compose)

Phase 5 case study demonstrating the **compose** transfer mode (PROTOCOL_SPEC.md §6.4) and the type-checked composition rules from §3.3.

## Story

Three specialist agents publish one skill each:

- `did:web:routing.example.com#optimize-route` — orders shipments by route distance.
- `did:web:inventory.example.com#check-stock` — annotates stops with stock levels.
- `did:web:eta.example.com#compute-eta` — computes arrival ETAs.

A **FulfillmentOrchestrator** at `did:web:fulfill.example.com` mirrors the three manifests locally and offers compose mode. A **ShipperClient** discovers the three specialists, then negotiates a compose agreement with the orchestrator that wires them as `routing → inventory → eta`. The orchestrator type-checks the pipeline (each step's outputs match the next step's inputs) and emits one composite skill manifest.

## Run

```bash
uv run python -m examples.03_logistics_pipeline.main
```

## What it demonstrates

1. **Discovery across three agents** — three independent Agent Cards and manifests fetched separately, in-process.
2. **Compose negotiation** — `transfer_mode=compose`, `proposed_terms.compose.steps=[routing, inventory, eta]`.
3. **Signed agreement** — same Ed25519 + did:web verification flow as examples 01 and 02.
4. **Type-checked composite synthesis** — sequential composition compatibility per §3.3 verified before the composite manifest is returned. Inputs come from step 1, outputs from step 3, and the schema_ref chain matches.
5. **Single-skill view** — the client now treats the composite as one skill (id `…#composite-<hash>`), even though three agents back it.

## Phase 4 scope note

This release implements compose where the receiving (orchestrator) agent has all step manifests in its **local** registry. The example mirrors the three specialist manifests into the orchestrator at startup to keep the cross-agent narrative honest. **Cross-agent skill resolution at compose time** — where the orchestrator fetches step manifests from foreign agents on demand — is a future enhancement (logged in `DESIGN_NOTES.md`). The composite-manifest output is identical either way; only the lookup path changes.

## Where this maps to the spec

| Spec section | Demonstrated by |
|---|---|
| §3.3 Composition compatibility | type-check pass before composite is emitted |
| §5 Negotiation FSM | propose → accept around compose terms |
| §6.4 compose | composite manifest returned by `polypact.transfer.compose` |
| §7 Identity (Phase 4) | step 3 verifies the orchestrator's JWS via did:web |
