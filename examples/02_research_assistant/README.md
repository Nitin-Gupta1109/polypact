# Example 02 — Research Assistant (teach)

Phase 5 case study demonstrating the **teach** transfer mode (PROTOCOL_SPEC.md §6.3).

## Story

- **ResearchSpecialist** owns a curated literature-review prompt template tuned over years. She is willing to *teach* it under a license but won't run it for anyone (the published manifest declares **only** `teach: supported`).
- **GeneralistOrchestrator** needs to brief his team next sprint. He doesn't want a per-invocation dependency on the specialist; he wants the artifact, locally, under license.
- The protocol delivers the value here: **structured cross-org transfer of a prompt artifact under explicit license terms**. The LLM call after transfer is elided — that's the initiator's framework's job, not the protocol's.

## Run

```bash
uv run python -m examples.02_research_assistant.main
```

## What it demonstrates

1. **Manifest with only `teach` enabled** — the spec's per-mode `supported` flag.
2. **Negotiation around a non-pricing transfer** — terms can be entirely about license, not money.
3. **Signed agreement** — Ed25519 + did:web verification, same as example 01.
4. **Artifact transfer** — the prompt template + `input_variables` + `license` arrive as a structured JSON-RPC response.
5. **Local execution** — the initiator renders the template (`{topic}`) and would hand it to its own LLM stack.

## Where this maps to the spec

| Spec section | Demonstrated by |
|---|---|
| §3 Manifest, transfer_modes | manifest declares `teach: supported`, others false |
| §6.3 teach | RPC response carries `artifact_type`, `artifact`, `license` |
| §7 Identity (Phase 4) | step 3 verifies the JWS via did:web |
