"""Pydantic models and state enum for the negotiation sub-protocol.

Implements the wire shapes from ``PROTOCOL_SPEC.md`` §5:

* ``NegotiationState`` — the seven-state machine from §5.1
* ``ProposedTerms`` — the negotiated terms block; per-mode params live in
  ``ModeTerms`` subfields (``lease``, ``teach``, ``compose``)
* ``Proposal`` — a single round of offered terms with proposer + timestamp
* ``NegotiationRecord`` — the complete persisted state of a negotiation
* ``Agreement`` — the canonical artifact produced on AGREED (§5.3)

Event types live alongside as Pydantic models so they can be logged and
replayed for audit. Phase 3 stubs ``signatures`` to ``{}`` per §5.3.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from polypact.manifest.schemas import DataHandling, Pricing, Terms

DEFAULT_NEGOTIATION_TTL_SECONDS = 600
"""Default negotiation TTL when callers don't specify (10 minutes)."""

TransferModeName = Literal["delegate", "lease", "teach", "compose"]


class NegotiationState(StrEnum):
    """The seven negotiation states from ``PROTOCOL_SPEC.md`` §5.1."""

    PROPOSED = "PROPOSED"
    AGREED = "AGREED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    DONE = "DONE"
    ABORTED = "ABORTED"
    EXPIRED = "EXPIRED"


TERMINAL_STATES: frozenset[NegotiationState] = frozenset(
    {
        NegotiationState.REJECTED,
        NegotiationState.DONE,
        NegotiationState.ABORTED,
        NegotiationState.EXPIRED,
    },
)


class _StrictBase(BaseModel):
    """Shared config for negotiation models."""

    model_config = ConfigDict(extra="forbid")


class LeaseTerms(_StrictBase):
    """Mode-specific terms for ``lease`` (``PROTOCOL_SPEC.md`` §6.2)."""

    max_invocations: int = Field(..., ge=1)
    ttl_seconds: int = Field(..., ge=1)


class ComposeTerms(_StrictBase):
    """Mode-specific terms for ``compose``."""

    compose_kind: Literal["sequential", "parallel"]
    steps: list[str] = Field(..., min_length=2, description="Skill IDs in order.")


class TeachTerms(_StrictBase):
    """Mode-specific terms for ``teach``."""

    artifact_type: Literal["prompt_template", "workflow", "tool_descriptor"] | None = None


class ProposedTerms(_StrictBase):
    """The terms block exchanged during negotiation.

    Reuses :class:`Pricing`, :class:`DataHandling`, and the SLA model from
    :mod:`polypact.manifest.schemas` to keep manifest-published terms and
    negotiated terms shape-compatible. Per-mode params live in optional
    ``lease``/``teach``/``compose`` subfields; only the field matching the
    selected ``transfer_mode`` is required at acceptance time (enforced by
    :mod:`polypact.negotiation.fsm`).
    """

    pricing: Pricing | None = None
    data_handling: DataHandling | None = None
    sla: Terms | None = None  # reuses the manifest Terms wrapper for SLA shape
    lease: LeaseTerms | None = None
    teach: TeachTerms | None = None
    compose: ComposeTerms | None = None


class Proposal(_StrictBase):
    """One round of offered terms."""

    terms: ProposedTerms
    rationale: str | None = None
    proposed_by: str = Field(..., description="DID of the proposing party.")
    proposed_at: datetime


class Parties(_StrictBase):
    """The two participants in a negotiation."""

    initiator: str
    provider: str


class Agreement(_StrictBase):
    """Canonical agreement artifact emitted on transition to ``AGREED`` (§5.3).

    ``signatures`` is stubbed to ``{}`` in Phases 1-3 per spec; real Ed25519
    JWS signing lands in Phase 4.
    """

    agreement_id: UUID = Field(default_factory=uuid4)
    negotiation_id: UUID
    skill_id: str
    transfer_mode: TransferModeName
    terms: ProposedTerms
    parties: Parties
    valid_from: datetime
    valid_until: datetime
    signatures: dict[str, str] = Field(default_factory=dict)


class NegotiationRecord(_StrictBase):
    """The full persisted state of a negotiation."""

    negotiation_id: UUID = Field(default_factory=uuid4)
    skill_id: str
    transfer_mode: TransferModeName
    initiator: str
    provider: str
    state: NegotiationState
    proposals: list[Proposal] = Field(default_factory=list, min_length=1)
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    agreement: Agreement | None = None
    rejection_reason: str | None = None

    @property
    def latest_terms(self) -> ProposedTerms:
        """The most recent proposal's terms — what would be accepted right now."""
        return self.proposals[-1].terms


# --- Event types (used by FSM and audit log) ---


class _EventBase(_StrictBase):
    """Common fields on every FSM event."""

    by: str = Field(..., description="DID of the agent triggering the event.")
    at: datetime


class ProposeEvent(_EventBase):
    """Initial event constructing a negotiation."""

    kind: Literal["propose"] = "propose"
    skill_id: str
    transfer_mode: TransferModeName
    initiator: str
    provider: str
    terms: ProposedTerms
    rationale: str | None = None
    negotiation_ttl_seconds: int = DEFAULT_NEGOTIATION_TTL_SECONDS


class CounterProposeEvent(_EventBase):
    """Either party offers replacement terms while in PROPOSED."""

    kind: Literal["counter_propose"] = "counter_propose"
    terms: ProposedTerms
    rationale: str | None = None
    negotiation_ttl_seconds: int = DEFAULT_NEGOTIATION_TTL_SECONDS


class AcceptEvent(_EventBase):
    """Either party accepts the most recent proposal."""

    kind: Literal["accept"] = "accept"


class RejectEvent(_EventBase):
    """Either party rejects the negotiation. Terminal."""

    kind: Literal["reject"] = "reject"
    reason: str | None = None


class TimeoutEvent(_EventBase):
    """Wall-clock expiry transitioned the negotiation to EXPIRED."""

    kind: Literal["timeout"] = "timeout"


NegotiationEvent = Annotated[
    ProposeEvent | CounterProposeEvent | AcceptEvent | RejectEvent | TimeoutEvent,
    Field(discriminator="kind"),
]


# --- Wire shapes for the four RPC methods (§5.2) ---


class ProposeRequest(_StrictBase):
    """Params for ``polypact.negotiate.propose`` (initiator → provider)."""

    agent_id: str
    trace_id: str
    skill_id: str
    transfer_mode: TransferModeName
    proposed_terms: ProposedTerms
    rationale: str | None = None
    negotiation_ttl_seconds: int = DEFAULT_NEGOTIATION_TTL_SECONDS


class CounterProposeRequest(_StrictBase):
    """Params for ``polypact.negotiate.counter_propose``."""

    agent_id: str
    trace_id: str
    negotiation_id: UUID
    proposed_terms: ProposedTerms
    rationale: str | None = None
    negotiation_ttl_seconds: int = DEFAULT_NEGOTIATION_TTL_SECONDS


class AcceptRequest(_StrictBase):
    """Params for ``polypact.negotiate.accept``."""

    agent_id: str
    trace_id: str
    negotiation_id: UUID


class RejectRequest(_StrictBase):
    """Params for ``polypact.negotiate.reject``."""

    agent_id: str
    trace_id: str
    negotiation_id: UUID
    reason: str | None = None


class NegotiationStatus(_StrictBase):
    """Response shape for propose/counter_propose/reject (no Agreement yet)."""

    negotiation_id: UUID
    state: NegotiationState
    expires_at: datetime
    rejection_reason: str | None = None
