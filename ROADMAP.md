# Roadmap

> Build in phases. After each phase, run all tests, update `DESIGN_NOTES.md` if needed, commit, tag, and stop to confirm before the next phase.

**Current phase: 4**

---

## Phase 0 — Project Initialization ✅

**Goal:** Working Python project skeleton.

**Tasks:**
- [x] Initialize repo with `pyproject.toml` (Python 3.11+, dependencies as listed in `INSTRUCTIONS.md`)
- [x] Set up `ruff`, `mypy`, `pytest` configs
- [x] Create empty package skeleton matching the layout in `INSTRUCTIONS.md`
- [x] Add `Makefile` (or `justfile`) with: `install`, `test`, `lint`, `format`, `typecheck`
- [x] Add `.gitignore`, `.github/workflows/ci.yml` (test + lint on push)
- [x] Create `DESIGN_NOTES.md` with a header section ready for entries
- [x] First commit: `chore: initialize project skeleton`

**Done when:** `make install && make test && make lint && make typecheck` all pass on an empty project.

---

## Phase 1 — Manifests + Transport (Conformance Level 1) ✅

**Goal:** Agents can advertise and discover skill manifests over HTTP.

**Tasks:**
- [x] Implement `polypact.manifest.schemas` — all Pydantic models from `PROTOCOL_SPEC.md` §3
- [x] Implement `polypact.manifest.validation` — beyond-schema rules
- [x] Unit tests for manifest schemas (valid examples, invalid examples, edge cases)
- [x] Implement `polypact.transport.jsonrpc` — encode/decode/dispatch
- [x] Implement `polypact.transport.http_server` — FastAPI mount point
- [x] Implement `polypact.transport.http_client` — httpx wrapper
- [x] Implement `polypact.discovery.agent_card` — `/.well-known/agent.json` with polypact extension
- [x] Implement `polypact.discovery.manifests` — list and fetch endpoints
- [x] Implement minimal `polypact.server.create_app`
- [x] Implement minimal `polypact.client` with `fetch_agent_card` and `list_manifests`
- [x] Integration test: `tests/integration/test_discovery.py` — Agent A discovers Agent B's manifests end-to-end

**Done when:**
- All tests pass
- `mypy --strict` clean
- An example script in `examples/00_discovery/` runs two agents and prints discovered manifests
- Tag: `phase-1-complete`

---

## Phase 2 — Composition Compatibility + Delegate (Conformance Level 2) ✅

**Goal:** Agents can check skill compatibility and perform basic task delegation.

**Tasks:**
- [x] Implement `polypact.manifest.compatibility` — sequential and parallel composition checks per §3.3
- [x] Add `polypact.discover.check_composition` RPC method
- [x] Implement `polypact.transfer.delegate` — basic task invocation
- [x] Implement `polypact.task.invoke` RPC
- [x] Server-side skill registration: `@app.skill(...)` decorator in `server.py`
- [x] Client-side delegation in `polypact.client.invoke_skill`
- [x] Unit tests for compatibility logic
- [x] Integration test: Agent A delegates a task to Agent B, gets result back

**Done when:**
- Compatibility check returns correct judgments for at least 5 test cases
- End-to-end delegation test passes
- Tag: `phase-2-complete`

---

## Phase 3 — Negotiation FSM (Conformance Level 3) ✅

**Goal:** Agents can negotiate skill use under explicit terms.

**Tasks:**
- [x] Implement `polypact.negotiation.schemas` per `PROTOCOL_SPEC.md` §5
- [x] Implement `polypact.negotiation.fsm` as a pure function — no I/O
- [x] Implement `polypact.negotiation.store` with an in-memory backend behind a Protocol interface
- [x] Implement `polypact.negotiation.coordinator` — handles RPC ↔ FSM ↔ store
- [x] Wire RPC methods: `polypact.negotiate.propose`, `counter_propose`, `accept`, `reject`
- [x] Unit tests covering all FSM transitions including invalid ones
- [x] Unit test: round-trip serialize → deserialize an Agreement
- [x] Integration test: full negotiation flow with one counter-proposal then accept
- [x] Integration test: rejection terminates negotiation cleanly
- [x] Integration test: timeout transitions PROPOSED → EXPIRED

**Done when:**
- FSM unit tests cover every documented transition (valid + invalid)
- Three integration tests pass
- Tag: `phase-3-complete`

---

## Phase 4 — Transfer Primitives (Conformance Level 4)

**Goal:** All four transfer modes work end-to-end.

**Tasks:**
- [ ] Implement `polypact.transfer.lease` with invocation counting and TTL
- [ ] Lease invocations decrement and reject when exhausted
- [ ] Implement `polypact.transfer.teach` with artifact packaging
- [ ] Implement `polypact.transfer.compose` with type-checked sequential and parallel pipelines
- [ ] Implement `polypact.transfer.invoker` to route based on agreement transfer_mode
- [ ] Phase 4 identity work: `did:web` resolution, Ed25519 signing of agreements
- [ ] Replace identity stubs; add signature verification before honoring agreements
- [ ] Integration tests for each primitive (one per mode)
- [ ] Integration test: lease expiry rejects further invocations with -32003
- [ ] Integration test: composition with mismatched I/O types rejected with -32004

**Done when:**
- All four transfer modes have passing integration tests
- Identity is real (no stubs in production paths)
- Tag: `phase-4-complete`

---

## Phase 5 — Case Studies

**Goal:** Three runnable examples demonstrating Polypact's value, suitable for inclusion in the paper.

**Tasks:**
- [ ] `examples/01_invoice_extraction/` — **Lease scenario.** A finance agent leases a document agent's invoice extractor for 50 invocations, paying per use.
- [ ] `examples/02_research_assistant/` — **Teach scenario.** A specialist research agent transfers a literature-review prompt template to a generalist orchestrator, which then runs it locally.
- [ ] `examples/03_logistics_pipeline/` — **Compose scenario.** Three agents (routing, inventory, ETA) compose into a unified fulfillment pipeline visible to a client agent as one skill.
- [ ] Each example: `README.md`, runnable `main.py`, sample data, expected output
- [ ] All three examples cited in the paper

**Done when:**
- Each example runs with one command
- Each produces output suitable for a paper figure
- Tag: `phase-5-complete`

---

## Phase 5b — Reference Adapter (Framework-Agnostic Validation)

**Goal:** Prove Polypact really is framework-agnostic by writing one adapter for an existing agent framework. The adapter wraps the framework's native skill format and exposes it via Polypact without modifying the framework itself.

This phase exists because "framework-agnostic" is a claim that's only credible if validated. One real adapter is enough; more can come later.

**Tasks:**
- [ ] Pick one target framework (default suggestion: a minimal LangChain or OpenClaw-style agent — final choice deferred to start of phase, see `INTEGRATIONS.md` §3)
- [ ] Implement `polypact.adapters.<framework>` that:
  - Reads native skills (e.g., LangChain `Tool` objects, or OpenClaw `SKILL.md` directories)
  - Generates a valid `SkillManifest` per skill
  - Routes incoming Polypact `task.invoke` calls to the native skill executor
  - Surfaces native errors as Polypact error codes
- [ ] One example: `examples/05_adapter_demo/` — same agent's skills accessed (a) natively and (b) via Polypact, producing identical results
- [ ] Document the adapter pattern in `INTEGRATIONS.md` so users can write their own
- [ ] Integration test: a Polypact client invokes an adapter-wrapped skill end-to-end

**Done when:**
- Adapter exists for at least one real framework
- The example demonstrates protocol parity with native invocation
- Pattern is documented well enough for someone else to write a second adapter without our help
- Tag: `phase-5b-complete`

---

## Phase 6 — Paper Artifacts

**Goal:** Materials ready for paper submission.

**Tasks:**
- [ ] Generate protocol diagrams (state machine, message flow, architecture) as SVG
- [ ] Generate evaluation tables from case study runs
- [ ] Write `EVALUATION.md` summarizing findings
- [ ] Final pass on `PROTOCOL_SPEC.md` to align with what was actually built
- [ ] Tag: `v0.1.0`
- [ ] Optional: package and publish to TestPyPI for paper-time install instructions

**Done when:** A reviewer cloning the repo and following `README.md` can reproduce all case studies in under 10 minutes.

---

## Stretch / Future

Out of scope for v0.1. See [`FUTURE_WORK.md`](./FUTURE_WORK.md) for the full plan, but in brief:

- **Knowledge federation** (`polypact.knowledge.*`) — cross-org KG queries, contributions, subscriptions
- **Memory federation** (`polypact.memory.*`) — sharing learned context between agents
- **Payment integration** — AP2 settlement on top of negotiated terms
- **Production identity** — HSM-backed keys, key rotation, revocation
- **Persistent NegotiationStore** — Postgres backend
- **Multi-language SDKs** — TypeScript, Go
- **Additional adapters** — for any agent framework that gains user demand

These belong in `FUTURE_WORK.md` and are explicitly reserved as protocol extensions in `PROTOCOL_SPEC.md` §10.
