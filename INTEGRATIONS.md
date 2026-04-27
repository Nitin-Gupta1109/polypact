# Integrations: Plugging Polypact Into Existing Frameworks

> Polypact is **framework-agnostic by design**. It does not assume your agent runs on LangChain, OpenClaw, NemoClaw, AutoGen, CrewAI, LangGraph, or anything else. The protocol speaks JSON-RPC over HTTP. The integration question is: how do you connect *your* agent's skills to *the protocol*?

This document explains the **adapter pattern** Polypact uses, gives concrete sketches for several common agent runtimes, and lays out the rules adapters must follow to remain spec-compliant.

## 1. The Adapter Pattern

```
┌────────────────────────────────────────────────┐
│              YOUR AGENT FRAMEWORK              │
│   (skills, tools, memory, model wiring,        │
│    orchestration — all unchanged)              │
└────────────────────┬───────────────────────────┘
                     │ native skill invocation
                     ▼
┌────────────────────────────────────────────────┐
│              POLYPACT ADAPTER                  │
│   - Maps native skill format → SkillManifest   │
│   - Hosts a Polypact HTTP server               │
│   - Translates incoming RPC → native calls     │
│   - Translates native errors → Polypact errors │
│   - Negotiation, agreements, transfer modes    │
└────────────────────┬───────────────────────────┘
                     │ Polypact protocol
                     ▼
              ┌──────────────┐
              │ Other agents │
              │ (any stack)  │
              └──────────────┘
```

**The adapter is the only framework-aware code.** The core protocol library (`polypact.*`) knows nothing about LangChain or OpenClaw and never will. This is what lets Polypact remain agnostic indefinitely.

## 2. Adapter Contract

Every adapter MUST provide:

### 2.1 Skill Discovery
A function that enumerates the host framework's skills and produces valid `SkillManifest` objects. The adapter chooses sensible defaults for fields the host doesn't natively express:

- `id`: derived from the agent's DID + skill name (`did:web:org.com#<skill-name>`)
- `io.inputs` / `io.outputs`: derived from the host's tool schema if available; otherwise declared by the operator
- `transfer_modes`: defaults to `delegate: true` only; operator opts into `lease`, `teach`, or `compose`
- `terms`: defaults to free, no SLA, EU processing; operator overrides

### 2.2 Invocation Bridge
An async function that, given an agreement and an input payload, calls the host's native skill executor and returns its output as a JSON-serializable dict.

```python
async def invoke_native(skill_id: str, input: dict, agreement: Agreement) -> dict:
    """Bridge a Polypact invocation to the host framework's native executor."""
```

### 2.3 Error Mapping
A mapping from host-framework exceptions to Polypact JSON-RPC error codes. At minimum:

| Host condition | Polypact error |
|---|---|
| Skill not found | -32001 (Unknown skill) |
| Input schema violation | -32602 (Invalid params, JSON-RPC standard) |
| Authorization failure | -32005 |
| Other | -32000 (generic) |

### 2.4 Lifecycle Hooks
- `on_startup`: register skills with the Polypact server, load any persisted agreements
- `on_shutdown`: gracefully terminate active leases, persist state if configured

## 3. Suggested Reference Adapter

The Phase 5b roadmap entry calls for **one** reference adapter. The choice matters less than the discipline of doing it — any concrete adapter validates the framework-agnostic claim. Below are sketches for several plausible targets so the maintainer can pick.

> **Important — verify before implementing.** The sketches below describe what an adapter *would* look like based on each framework's general shape. **Before writing the chosen adapter, the implementer must consult the target framework's current documentation** (links provided) to confirm class names, decorator signatures, and skill-loading APIs. These details change between framework versions.

### 3.1 LangChain Adapter (recommended for first pass)

**Why:** Widest reach, simplest skill format, well-documented Tool API.

**Native unit:** `langchain.tools.BaseTool` — has `name`, `description`, `args_schema` (Pydantic).

**Sketch:**

```python
from langchain.tools import BaseTool
from polypact.manifest import SkillManifest, IOSpec
from polypact.adapters import Adapter

class LangChainAdapter(Adapter):
    def __init__(self, agent_did: str, tools: list[BaseTool]):
        self.agent_did = agent_did
        self.tools = {t.name: t for t in tools}

    def discover(self) -> list[SkillManifest]:
        return [self._tool_to_manifest(t) for t in self.tools.values()]

    async def invoke(self, skill_id, input, agreement):
        tool_name = skill_id.split("#", 1)[1]
        tool = self.tools[tool_name]
        return await tool.ainvoke(input)

    def _tool_to_manifest(self, tool: BaseTool) -> SkillManifest:
        # Map args_schema → IOSpec.inputs
        # Description → manifest.description
        # Default to delegate-only; operator config can promote to lease/teach
        ...
```

**Verification needed:** confirm current `BaseTool` interface (`ainvoke` signature, `args_schema` access pattern) against LangChain's latest docs at https://python.langchain.com/docs/.

### 3.2 OpenClaw-Style Adapter

**Why:** Skills are filesystem directories with `SKILL.md` metadata — a clean, simple format that's representative of "personal agent" frameworks.

**Native unit:** A directory containing `SKILL.md` plus tool descriptors and prompts. Skills are loaded from a workspace path.

**Sketch:**

```python
class OpenClawStyleAdapter(Adapter):
    def __init__(self, agent_did: str, workspace_path: Path):
        self.agent_did = agent_did
        self.workspace = workspace_path

    def discover(self) -> list[SkillManifest]:
        manifests = []
        for skill_dir in self.workspace.glob("skills/*/"):
            md = skill_dir / "SKILL.md"
            if md.exists():
                manifests.append(self._parse_skill_md(skill_dir, md))
        return manifests

    async def invoke(self, skill_id, input, agreement):
        # Delegate to the local agent runtime to execute the named skill
        ...
```

**Verification needed:** before implementing, confirm the current `SKILL.md` schema and skill-loading mechanism in the target framework's documentation. Skill formats evolve; do not rely on this sketch's field assumptions.

**Notes:**
- This adapter pattern is well-suited to "teach" mode: the entire skill directory can be packaged as the artifact transferred during a `polypact.transfer.teach` operation.
- Operators must explicitly opt into `teach`; default is `delegate` only, since teaching exposes prompts and tool descriptors.

### 3.3 Hardened-Runtime Adapter (NemoClaw-style)

**Why:** Demonstrates that Polypact works when the host runtime adds security policy, sandboxing, and audit on top of the agent — common in regulated enterprise deployments.

The adapter pattern is identical to the OpenClaw-style one, with two additions:

1. **Policy gate before invocation.** The adapter consults the host runtime's policy engine (sandbox controls, network policy, credential isolation) before forwarding the call. A policy denial maps to Polypact error `-32005` (Authorization failed).
2. **Audit propagation.** Every Polypact message becomes an audit event in the host runtime's audit log, with the Polypact `trace_id` as the correlation key.

This is the integration story for organizations that need agent federation *and* compliance — Polypact's negotiated terms (`data_handling.processing_locations`, `data_handling.subprocessors_allowed`) become enforceable when the host runtime is policy-gated.

**Verification needed:** the policy gate API, audit hooks, and sandbox interception points are runtime-specific. Read the target runtime's security architecture docs before wiring the adapter.

### 3.4 Custom / In-House Agent Adapter

For bespoke agents, the adapter is whatever bridges your skill registry to the protocol. The contract in §2 is the only requirement.

A minimal custom adapter is roughly 100–200 lines of Python. The reference implementation provides `polypact.adapters.base.Adapter` as a starting point.

## 4. Knowledge & Memory Layer Integration (Future)

Many agent stacks pair their runtime with a knowledge layer — vector stores, knowledge graphs (Cognee-style backed by graph databases), document indexes, episodic memory. For v0.1, **Polypact does not federate these**.

When `polypact.knowledge.*` and `polypact.memory.*` extensions land (see `PROTOCOL_SPEC.md` §10), the adapter pattern extends naturally:

```
┌─────────────────────────────────────┐
│         Agent Framework             │
│  ┌─────────┐    ┌──────────────┐    │
│  │ Skills  │    │  KG / Memory │    │
│  └────┬────┘    └──────┬───────┘    │
└───────┼────────────────┼────────────┘
        │                │
   ┌────▼────┐      ┌────▼─────┐
   │ Skill   │      │Knowledge │ ◄── Future extension
   │ Adapter │      │ Adapter  │
   └─────────┘      └──────────┘
        │                │
        └─── Polypact ───┘
```

The same negotiation FSM and identity layer apply; only the methods and terms differ. This is why the spec reserves namespace and signals support via the Agent Card's `extensions` field — adapters built today can declare `extensions: ["knowledge:0.1-draft"]` once the standard lands without restructuring.

## 5. Adapter Authoring Checklist

When writing a new adapter:

- [ ] Pick the smallest reasonable native unit (one tool, one skill directory, one workflow node)
- [ ] **Read the target framework's current documentation** to confirm class names, signatures, and skill-loading APIs — do not assume from memory
- [ ] Map it to a `SkillManifest`; default to `delegate` only
- [ ] Implement the invocation bridge end-to-end before adding lease/teach/compose
- [ ] Map native errors to Polypact error codes (§2.3)
- [ ] Write at least one integration test that round-trips through the adapter
- [ ] Document any framework-specific assumptions in the adapter's README — including the framework version and docs URL you verified against
- [ ] Default conservative on transfer modes: never auto-enable `teach` (it transfers prompts and proprietary logic)
- [ ] Honor the host runtime's policy and audit if present (§3.3)

## 6. What Adapters MUST NOT Do

- Modify the Polypact protocol surface to fit a framework's quirks. If a framework can't fit the contract, write an issue first; don't fork the wire format.
- Bypass the negotiation FSM. Even a "trusted" adapter must produce real agreements — they're audit artifacts, not optional.
- Expose internal state (memory, prompts, tool implementations) via `delegate` mode. Internal exposure is the exclusive job of `teach`, with explicit operator opt-in.
- Persist agreements without operator-configured storage. Adapters do not silently retain cross-org artifacts.

---

The adapter pattern is the load-bearing claim of Polypact's framework-agnostic design. If a framework can't be adapted in under ~500 lines of Python, that's a protocol bug — open an issue.
