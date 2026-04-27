"""Tests for the pure negotiation FSM (PROTOCOL_SPEC.md §5.1).

Covers every documented transition (valid + invalid) plus lazy expiry.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from polypact.errors import NegotiationStateError
from polypact.negotiation import (
    AcceptEvent,
    CounterProposeEvent,
    LeaseTerms,
    NegotiationRecord,
    NegotiationState,
    ProposedTerms,
    ProposeEvent,
    RejectEvent,
    TimeoutEvent,
    initial,
    step,
)

T0 = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _propose_event(*, ttl: int = 600) -> ProposeEvent:
    return ProposeEvent(
        by="did:web:a.com",
        at=T0,
        skill_id="did:web:b.com#extract",
        transfer_mode="lease",
        initiator="did:web:a.com",
        provider="did:web:b.com",
        terms=ProposedTerms(lease=LeaseTerms(max_invocations=10, ttl_seconds=3600)),
        negotiation_ttl_seconds=ttl,
    )


def _record() -> NegotiationRecord:
    return initial(_propose_event())


# --- Valid transitions ---


def test_initial_creates_proposed_record() -> None:
    record = _record()
    assert record.state == NegotiationState.PROPOSED
    assert len(record.proposals) == 1
    assert record.expires_at == T0 + timedelta(seconds=600)
    assert record.agreement is None


def test_counter_propose_stays_in_proposed_and_resets_expiry() -> None:
    record = _record()
    later = T0 + timedelta(seconds=10)
    new_terms = ProposedTerms(lease=LeaseTerms(max_invocations=20, ttl_seconds=7200))
    event = CounterProposeEvent(
        by="did:web:b.com",
        at=later,
        terms=new_terms,
        negotiation_ttl_seconds=900,
    )
    next_record = step(record, event, now=later)
    assert next_record.state == NegotiationState.PROPOSED
    assert len(next_record.proposals) == 2
    assert next_record.latest_terms == new_terms
    assert next_record.expires_at == later + timedelta(seconds=900)


def test_accept_transitions_to_agreed_with_agreement() -> None:
    record = _record()
    later = T0 + timedelta(seconds=5)
    next_record = step(record, AcceptEvent(by="did:web:b.com", at=later), now=later)
    assert next_record.state == NegotiationState.AGREED
    assert next_record.agreement is not None
    assert next_record.agreement.skill_id == record.skill_id
    assert next_record.agreement.transfer_mode == "lease"
    assert next_record.agreement.signatures == {}
    # Lease TTL drives valid_until.
    assert next_record.agreement.valid_until == later + timedelta(seconds=3600)


def test_reject_transitions_to_rejected_with_reason() -> None:
    record = _record()
    later = T0 + timedelta(seconds=5)
    event = RejectEvent(by="did:web:b.com", at=later, reason="terms too low")
    next_record = step(record, event, now=later)
    assert next_record.state == NegotiationState.REJECTED
    assert next_record.rejection_reason == "terms too low"


def test_explicit_timeout_event_from_proposed_yields_expired() -> None:
    """Explicit TimeoutEvent (not lazy) drives PROPOSED → EXPIRED.

    Use a ``now`` that's still inside the TTL so lazy expiry doesn't fire first;
    this isolates the explicit timeout path.
    """
    record = _record()
    later = record.expires_at - timedelta(seconds=1)
    next_record = step(record, TimeoutEvent(by="did:web:b.com", at=later), now=later)
    assert next_record.state == NegotiationState.EXPIRED


def test_lazy_expiry_blocks_subsequent_events_with_terminal_error() -> None:
    record = _record()
    later = record.expires_at + timedelta(seconds=1)
    with pytest.raises(NegotiationStateError, match="terminal state EXPIRED"):
        step(record, AcceptEvent(by="did:web:a.com", at=later), now=later)


def test_lazy_expiry_blocks_timeout_event_too() -> None:
    """A TimeoutEvent arriving after lazy expiry already fired is itself rejected.

    The expiry happened during the read; the FSM is in EXPIRED (terminal) and
    refuses any further events, including another timeout.
    """
    record = _record()
    later = record.expires_at + timedelta(seconds=1)
    with pytest.raises(NegotiationStateError, match="terminal state EXPIRED"):
        step(record, TimeoutEvent(by="did:web:b.com", at=later), now=later)


# --- Invalid transitions ---


def test_propose_event_via_step_is_rejected() -> None:
    record = _record()
    with pytest.raises(NegotiationStateError, match="initial event"):
        step(record, _propose_event(), now=T0 + timedelta(seconds=1))


def test_counter_propose_after_accept_is_rejected() -> None:
    record = _record()
    later = T0 + timedelta(seconds=5)
    accepted = step(record, AcceptEvent(by="did:web:b.com", at=later), now=later)
    later2 = later + timedelta(seconds=1)
    event = CounterProposeEvent(
        by="did:web:a.com",
        at=later2,
        terms=ProposedTerms(),
    )
    with pytest.raises(NegotiationStateError, match="counter_propose requires PROPOSED"):
        step(accepted, event, now=later2)


def test_accept_after_reject_is_rejected() -> None:
    record = _record()
    later = T0 + timedelta(seconds=5)
    rejected = step(record, RejectEvent(by="did:web:b.com", at=later), now=later)
    later2 = later + timedelta(seconds=1)
    with pytest.raises(NegotiationStateError, match="terminal state REJECTED"):
        step(rejected, AcceptEvent(by="did:web:a.com", at=later2), now=later2)


def test_reject_after_expiry_is_rejected() -> None:
    record = _record()
    # Trigger expiry via the explicit-timeout path (now still inside TTL).
    pre_expiry = record.expires_at - timedelta(seconds=1)
    expired = step(record, TimeoutEvent(by="did:web:b.com", at=pre_expiry), now=pre_expiry)
    later = pre_expiry + timedelta(seconds=1)
    with pytest.raises(NegotiationStateError, match="terminal state EXPIRED"):
        step(expired, RejectEvent(by="did:web:a.com", at=later), now=later)


def test_timeout_from_agreed_is_rejected() -> None:
    """AGREED is not terminal in Phase 3 (Phase 4 adds AGREED → EXECUTING),
    so timeout's branch-level check fires rather than the terminal-state guard.
    """
    record = _record()
    later = T0 + timedelta(seconds=5)
    agreed = step(record, AcceptEvent(by="did:web:b.com", at=later), now=later)
    later2 = later + timedelta(seconds=1)
    with pytest.raises(NegotiationStateError, match="timeout valid only from"):
        step(agreed, TimeoutEvent(by="did:web:b.com", at=later2), now=later2)
