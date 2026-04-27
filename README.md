# Polypact

> **Research-stage**, **framework-agnostic** protocol for negotiated skill transfer between cross-organization AI agents.

Polypact is a federation layer. It does **not** replace your agent runtime — whether that's a custom Python agent, an OpenClaw-style assistant, an NVIDIA NemoClaw enterprise deployment, a LangGraph workflow, or anything else. Instead, it gives any of them a common protocol to **discover, negotiate, and share skills across organizational boundaries** under explicit terms.

It extends [Google A2A](https://github.com/a2aproject/A2A) with primitives for agents to **lend, teach, and compose** capabilities — going beyond opaque task delegation to support genuine skill sharing across trust boundaries.

This repository accompanies a research paper (in preparation).

## What's Different

| | A2A / ACP | Polypact |
|---|---|---|
| Task delegation | ✅ | ✅ |
| Capability discovery | ✅ (Agent Cards) | ✅ (extended manifests) |
| **Term negotiation** | ❌ | ✅ (propose / counter / accept FSM) |
| **Skill leasing** | ❌ | ✅ |
| **Skill teaching** (artifact transfer) | ❌ | ✅ |
| **Type-checked composition** | ❌ | ✅ |
| Cross-org identity | partial | DID-based (Phase 4) |
| Framework-agnostic | partial | ✅ (adapter-based) |

## Where Polypact Sits

```
   Your agent framework         Their agent framework
   (OpenClaw / NemoClaw /       (whatever it is)
    LangGraph / custom)
          │                              │
          ▼                              ▼
   ┌─────────────┐                ┌─────────────┐
   │  Polypact   │ ◄── protocol ──►│  Polypact   │
   │   Adapter   │                │   Adapter   │
   └─────────────┘                └─────────────┘
          ▲                              ▲
          └─────── tools / KGs ──────────┘
                  (untouched)
```

Polypact is a thin **adapter** in front of your existing agent. Your skills, tools, and knowledge layers stay where they are. The adapter exposes them under a negotiated, opacity-preserving protocol that other organizations' agents can talk to. See [INTEGRATIONS.md](./INTEGRATIONS.md) for how this works in practice.

## Status

| Phase | Status |
|---|---|
| 0 — Initialization | 🚧 |
| 1 — Manifests + Transport | ⏳ |
| 2 — Compatibility + Delegate | ⏳ |
| 3 — Negotiation FSM | ⏳ |
| 4 — Transfer Primitives + Identity | ⏳ |
| 5 — Case Studies | ⏳ |
| 6 — Paper Artifacts | ⏳ |

## Quick Start

```bash
# Once Phase 1 is complete
uv sync
make test
python -m examples.00_discovery
```

## Repository Map

- [`PROTOCOL_SPEC.md`](./PROTOCOL_SPEC.md) — wire-level protocol specification (normative)
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — code architecture and module breakdown
- [`INTEGRATIONS.md`](./INTEGRATIONS.md) — how to plug Polypact into existing agent frameworks
- [`ROADMAP.md`](./ROADMAP.md) — phased build plan
- [`FUTURE_WORK.md`](./FUTURE_WORK.md) — what's intentionally deferred (KG federation, memory sharing, payments)
- [`INSTRUCTIONS.md`](./INSTRUCTIONS.md) — instructions for AI assistants contributing to the project
- [`CLAUDE.md`](./CLAUDE.md) — persistent context for Claude Code
- [`DESIGN_NOTES.md`](./DESIGN_NOTES.md) — log of design decisions and deviations from spec

## Scope

**v0.1 is about skills.** Cross-org agent collaboration breaks down today not because agents can't compute, but because they can't safely share what they're good at across trust boundaries. Polypact v0.1 fixes that one problem.

**Knowledge-graph federation, memory sharing, and payment** are deliberately **out of scope** for v0.1 but reserved as protocol extensions — see [FUTURE_WORK.md](./FUTURE_WORK.md). The protocol is designed so they can be added without breaking changes.

## Citing

A preprint will be available on arXiv. Citation details TBD.

## License

TBD — likely Apache 2.0 to match the A2A ecosystem.
