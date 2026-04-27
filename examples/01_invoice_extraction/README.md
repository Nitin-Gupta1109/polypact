# Example 01 — Invoice Extraction (lease)

Phase 5 case study demonstrating the **lease** transfer mode (PROTOCOL_SPEC.md §6.2).

## Story

- **CompanyA Finance Agent** needs to process a Q3 close batch of 50 invoices.
- **CompanyB Document Agent** publishes an `extract-invoice` skill at $0.05/invocation, supports lease for up to 1000 invocations / 24 h, and signs agreements with Ed25519.
- A lease saves CompanyA the negotiation overhead per call: one signed agreement covers the whole batch.

## Run

```bash
uv run python -m examples.01_invoice_extraction.main
```

## What it demonstrates

1. **Discovery** — fetching the Agent Card and the manifest.
2. **Negotiation** — counter-offer on price ($0.05 published → $0.04 in agreement); lease parameters set to the batch size.
3. **Signed agreement** — provider signs with Ed25519; client resolves the provider's `did:web` DID document and verifies before honoring.
4. **Lease invocations** — 50 successful calls, with invocation counter visible.
5. **Lease enforcement** — the 51st call is rejected with `AgreementViolatedError` (`-32003 Agreement violated`), proving the budget is enforced server-side.

## Where this maps to the spec

| Spec section | Demonstrated by |
|---|---|
| §3 Manifest | `build_invoice_manifest()` |
| §5 Negotiation FSM | `propose → accept` flow |
| §5.3 Agreement | signed agreement printed in step 2 |
| §6.2 lease | invocation budget enforced in step 5 |
| §7 Identity (Phase 4) | step 3 verifies the provider's JWS via did:web |
