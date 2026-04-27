"""Coordinator: glues FSM, store, and the wire shapes together.

The server's RPC handlers call into :class:`NegotiationCoordinator`; the
coordinator translates wire requests into FSM events, persists results, and
returns the freshly transitioned record. Lazy expiry is applied here on every
read so an expired negotiation never serves a stale state.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from polypact.errors import (
    AuthorizationFailedError,
    UnknownSkillError,
)
from polypact.manifest.registry import ManifestStore
from polypact.negotiation.fsm import _maybe_expire, initial, now_utc, step
from polypact.negotiation.schemas import (
    AcceptEvent,
    AcceptRequest,
    CounterProposeEvent,
    CounterProposeRequest,
    NegotiationRecord,
    ProposeEvent,
    ProposeRequest,
    RejectEvent,
    RejectRequest,
    TimeoutEvent,
)
from polypact.negotiation.store import NegotiationStore, UnknownNegotiationError

logger = logging.getLogger(__name__)


class NegotiationCoordinator:
    """Bridges RPC requests, the FSM, and the store.

    A single coordinator instance corresponds to one provider agent; it owns
    the manifest store (to validate skill IDs on propose) and the negotiation
    store (to persist records).
    """

    def __init__(
        self,
        *,
        provider_agent_id: str,
        manifests: ManifestStore,
        store: NegotiationStore,
    ) -> None:
        self.provider_agent_id = provider_agent_id
        self._manifests = manifests
        self._store = store

    def get(self, negotiation_id: UUID, *, now: datetime | None = None) -> NegotiationRecord:
        """Return a record, applying lazy expiry."""
        record = self._store.get(negotiation_id)
        return self._refresh(record, now or now_utc())

    def propose(
        self,
        request: ProposeRequest,
        *,
        now: datetime | None = None,
    ) -> NegotiationRecord:
        """Handle ``polypact.negotiate.propose``.

        Validates that the requested skill is in our manifest store and that
        the transfer mode is supported by that manifest. Creates and persists
        the new :class:`NegotiationRecord`.
        """
        when = now or now_utc()
        manifest = self._manifests.get(request.skill_id)  # raises UnknownSkillError
        mode = getattr(manifest.transfer_modes, request.transfer_mode, None)
        if mode is None or not mode.supported:
            msg = (
                f"skill {request.skill_id!r} does not support transfer_mode "
                f"{request.transfer_mode!r}"
            )
            raise UnknownSkillError(msg)
        event = ProposeEvent(
            by=request.agent_id,
            at=when,
            skill_id=request.skill_id,
            transfer_mode=request.transfer_mode,
            initiator=request.agent_id,
            provider=self.provider_agent_id,
            terms=request.proposed_terms,
            rationale=request.rationale,
            negotiation_ttl_seconds=request.negotiation_ttl_seconds,
        )
        record = initial(event)
        self._store.put(record)
        logger.info(
            "negotiation.transition",
            extra={
                "negotiation_id": str(record.negotiation_id),
                "from_state": None,
                "to_state": record.state,
                "by": request.agent_id,
            },
        )
        return record

    def counter_propose(
        self,
        request: CounterProposeRequest,
        *,
        now: datetime | None = None,
    ) -> NegotiationRecord:
        """Handle ``polypact.negotiate.counter_propose``."""
        when = now or now_utc()
        record = self._authorized_record(request.negotiation_id, request.agent_id, when)
        event = CounterProposeEvent(
            by=request.agent_id,
            at=when,
            terms=request.proposed_terms,
            rationale=request.rationale,
            negotiation_ttl_seconds=request.negotiation_ttl_seconds,
        )
        return self._apply_and_store(record, event, when)

    def accept(
        self,
        request: AcceptRequest,
        *,
        now: datetime | None = None,
    ) -> NegotiationRecord:
        """Handle ``polypact.negotiate.accept``."""
        when = now or now_utc()
        record = self._authorized_record(request.negotiation_id, request.agent_id, when)
        event = AcceptEvent(by=request.agent_id, at=when)
        return self._apply_and_store(record, event, when)

    def reject(
        self,
        request: RejectRequest,
        *,
        now: datetime | None = None,
    ) -> NegotiationRecord:
        """Handle ``polypact.negotiate.reject``."""
        when = now or now_utc()
        record = self._authorized_record(request.negotiation_id, request.agent_id, when)
        event = RejectEvent(by=request.agent_id, at=when, reason=request.reason)
        return self._apply_and_store(record, event, when)

    def expire(
        self,
        negotiation_id: UUID,
        *,
        now: datetime | None = None,
    ) -> NegotiationRecord:
        """Force a negotiation through ``timeout`` (used by tests / janitors)."""
        when = now or now_utc()
        record = self._fetch(negotiation_id)
        event = TimeoutEvent(by=self.provider_agent_id, at=when)
        return self._apply_and_store(record, event, when, refresh_first=False)

    # --- internals ---

    def _fetch(self, negotiation_id: UUID) -> NegotiationRecord:
        try:
            return self._store.get(negotiation_id)
        except UnknownNegotiationError as exc:
            msg = f"unknown negotiation: {negotiation_id}"
            raise UnknownSkillError(msg) from exc

    def _authorized_record(
        self,
        negotiation_id: UUID,
        agent_id: str,
        now: datetime,
    ) -> NegotiationRecord:
        record = self._fetch(negotiation_id)
        if agent_id not in (record.initiator, record.provider):
            msg = (
                f"agent {agent_id!r} is not a party to negotiation "
                f"{negotiation_id} (initiator={record.initiator}, "
                f"provider={record.provider})"
            )
            raise AuthorizationFailedError(msg)
        return self._refresh(record, now)

    def _refresh(
        self,
        record: NegotiationRecord,
        now: datetime,
    ) -> NegotiationRecord:
        refreshed = _maybe_expire(record, now)
        if refreshed is not record:
            self._store.put(refreshed)
        return refreshed

    def _apply_and_store(
        self,
        record: NegotiationRecord,
        event: object,
        when: datetime,
        *,
        refresh_first: bool = True,
    ) -> NegotiationRecord:
        previous_state = record.state
        if refresh_first:
            record = self._refresh(record, when)
        new_record = step(record, event, now=when)  # type: ignore[arg-type]
        self._store.put(new_record)
        logger.info(
            "negotiation.transition",
            extra={
                "negotiation_id": str(new_record.negotiation_id),
                "from_state": previous_state,
                "to_state": new_record.state,
                "event": type(event).__name__,
            },
        )
        return new_record
