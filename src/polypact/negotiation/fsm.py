"""The negotiation finite state machine — a pure function over records.

``step(record, event, now)`` returns a new :class:`NegotiationRecord` reflecting
the transition. No I/O, no logging, no side effects — the coordinator wires
this to the store and emits log events.

Lazy expiry: whenever ``now >= record.expires_at`` and the state is still
``PROPOSED``, the FSM treats the call as if a ``TimeoutEvent`` had landed first
and the original event applied to an ``EXPIRED`` record (which then rejects).

Transition table (``PROTOCOL_SPEC.md`` §5.1):

==========  ====================  ============
From        Event                 To
==========  ====================  ============
PROPOSED    counter_propose       PROPOSED
PROPOSED    accept                AGREED
PROPOSED    reject                REJECTED
PROPOSED    timeout               EXPIRED
AGREED      timeout               EXPIRED       (Phase 4 wires execute paths)
==========  ====================  ============

Anything else raises :class:`NegotiationStateError`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from polypact.errors import NegotiationStateError
from polypact.negotiation.schemas import (
    TERMINAL_STATES,
    AcceptEvent,
    Agreement,
    CounterProposeEvent,
    NegotiationEvent,
    NegotiationRecord,
    NegotiationState,
    Parties,
    Proposal,
    ProposeEvent,
    RejectEvent,
    TimeoutEvent,
)


def initial(event: ProposeEvent) -> NegotiationRecord:
    """Build the initial :class:`NegotiationRecord` from a propose event."""
    return NegotiationRecord(
        skill_id=event.skill_id,
        transfer_mode=event.transfer_mode,
        initiator=event.initiator,
        provider=event.provider,
        state=NegotiationState.PROPOSED,
        proposals=[
            Proposal(
                terms=event.terms,
                rationale=event.rationale,
                proposed_by=event.by,
                proposed_at=event.at,
            ),
        ],
        expires_at=event.at + timedelta(seconds=event.negotiation_ttl_seconds),
        created_at=event.at,
        updated_at=event.at,
    )


def step(
    record: NegotiationRecord,
    event: NegotiationEvent,
    *,
    now: datetime,
) -> NegotiationRecord:
    """Apply ``event`` to ``record`` and return the resulting record.

    Raises :class:`NegotiationStateError` for any invalid transition. The
    caller is responsible for persistence.
    """
    expired = _maybe_expire(record, now)
    if expired is not record:
        record = expired

    if record.state in TERMINAL_STATES:
        msg = (
            f"negotiation {record.negotiation_id} is in terminal state "
            f"{record.state}; no further transitions allowed"
        )
        raise NegotiationStateError(msg)

    if isinstance(event, ProposeEvent):
        msg = "ProposeEvent only valid as the initial event; use fsm.initial()"
        raise NegotiationStateError(msg)

    if isinstance(event, CounterProposeEvent):
        return _counter_propose(record, event)
    if isinstance(event, AcceptEvent):
        return _accept(record, event)
    if isinstance(event, RejectEvent):
        return _reject(record, event)
    if isinstance(event, TimeoutEvent):
        return _timeout(record, event)

    msg = f"unhandled event type: {type(event).__name__}"
    raise NegotiationStateError(msg)


def _maybe_expire(record: NegotiationRecord, now: datetime) -> NegotiationRecord:
    """Return an EXPIRED record if expiry has passed, else the original."""
    if record.state != NegotiationState.PROPOSED:
        return record
    if now < record.expires_at:
        return record
    return record.model_copy(
        update={"state": NegotiationState.EXPIRED, "updated_at": now},
    )


def _counter_propose(
    record: NegotiationRecord,
    event: CounterProposeEvent,
) -> NegotiationRecord:
    if record.state != NegotiationState.PROPOSED:
        msg = f"counter_propose requires PROPOSED, got {record.state}"
        raise NegotiationStateError(msg)
    new_proposals = [
        *record.proposals,
        Proposal(
            terms=event.terms,
            rationale=event.rationale,
            proposed_by=event.by,
            proposed_at=event.at,
        ),
    ]
    return record.model_copy(
        update={
            "proposals": new_proposals,
            "expires_at": event.at + timedelta(seconds=event.negotiation_ttl_seconds),
            "updated_at": event.at,
        },
    )


def _accept(record: NegotiationRecord, event: AcceptEvent) -> NegotiationRecord:
    if record.state != NegotiationState.PROPOSED:
        msg = f"accept requires PROPOSED, got {record.state}"
        raise NegotiationStateError(msg)
    agreement = _build_agreement(record, event_at=event.at)
    return record.model_copy(
        update={
            "state": NegotiationState.AGREED,
            "agreement": agreement,
            "updated_at": event.at,
        },
    )


def _reject(record: NegotiationRecord, event: RejectEvent) -> NegotiationRecord:
    if record.state != NegotiationState.PROPOSED:
        msg = f"reject requires PROPOSED, got {record.state}"
        raise NegotiationStateError(msg)
    return record.model_copy(
        update={
            "state": NegotiationState.REJECTED,
            "rejection_reason": event.reason,
            "updated_at": event.at,
        },
    )


def _timeout(record: NegotiationRecord, event: TimeoutEvent) -> NegotiationRecord:
    if record.state not in (NegotiationState.PROPOSED, NegotiationState.EXECUTING):
        msg = f"timeout valid only from PROPOSED or EXECUTING, got {record.state}"
        raise NegotiationStateError(msg)
    return record.model_copy(
        update={"state": NegotiationState.EXPIRED, "updated_at": event.at},
    )


def _build_agreement(record: NegotiationRecord, *, event_at: datetime) -> Agreement:
    """Build the :class:`Agreement` artifact for an accepted negotiation.

    ``valid_until`` is taken from the lease TTL when ``transfer_mode == 'lease'``
    and from the negotiation expiry otherwise. Phase 4 will refine per-mode
    ``valid_until`` rules.
    """
    terms = record.latest_terms
    valid_until = record.expires_at
    if record.transfer_mode == "lease" and terms.lease is not None:
        valid_until = event_at + timedelta(seconds=terms.lease.ttl_seconds)
    return Agreement(
        agreement_id=uuid4(),
        negotiation_id=record.negotiation_id,
        skill_id=record.skill_id,
        transfer_mode=record.transfer_mode,
        terms=terms,
        parties=Parties(initiator=record.initiator, provider=record.provider),
        valid_from=event_at,
        valid_until=valid_until,
        signatures={},
    )


def now_utc() -> datetime:
    """Return the current UTC datetime; provided here for FSM consumers to share."""
    return datetime.now(UTC)
