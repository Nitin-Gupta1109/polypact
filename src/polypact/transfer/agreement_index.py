"""Index agreements by ``agreement_id`` for fast lookup at invoke time.

Agreements are owned by negotiations (``NegotiationRecord.agreement``); this
module provides a thin wrapper that walks the negotiation store and returns
the matching :class:`Agreement`. In v0.1 the walk is acceptable; later phases
may swap in a persistent backend with a real index.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from polypact.errors import AgreementViolatedError, AuthorizationFailedError
from polypact.negotiation import (
    Agreement,
    NegotiationRecord,
    NegotiationState,
    NegotiationStore,
)


class AgreementIndex:
    """Read-only lookup of agreements indexed by ``agreement_id``.

    Backed by a :class:`NegotiationStore`. Filters out agreements whose
    parent negotiation is not in ``AGREED`` or ``EXECUTING`` state — those
    agreements should never be honored on the wire.
    """

    def __init__(self, store: NegotiationStore) -> None:
        self._store = store

    def find(self, agreement_id: UUID) -> tuple[NegotiationRecord, Agreement]:
        """Return ``(record, agreement)`` for ``agreement_id``.

        Raises:
            AgreementViolatedError: If no live agreement matches.
        """
        for record in self._store.list():
            if record.agreement is None:
                continue
            if record.agreement.agreement_id != agreement_id:
                continue
            if record.state not in (NegotiationState.AGREED, NegotiationState.EXECUTING):
                msg = (
                    f"agreement {agreement_id} exists but its negotiation is in "
                    f"state {record.state}"
                )
                raise AgreementViolatedError(msg)
            return record, record.agreement
        msg = f"no agreement found for id {agreement_id}"
        raise AgreementViolatedError(msg)

    def assert_caller_is_party(
        self,
        record: NegotiationRecord,
        caller: str,
    ) -> None:
        """Reject calls from agents who aren't a party to the agreement."""
        if caller not in (record.initiator, record.provider):
            msg = (
                f"agent {caller!r} is not a party to agreement "
                f"{record.agreement.agreement_id if record.agreement else '?'}"
            )
            raise AuthorizationFailedError(msg)

    def assert_within_validity_window(
        self,
        agreement: Agreement,
        *,
        now: datetime,
    ) -> None:
        """Reject calls outside ``[valid_from, valid_until]``."""
        if now < agreement.valid_from:
            msg = f"agreement {agreement.agreement_id} not yet valid"
            raise AgreementViolatedError(msg)
        if now > agreement.valid_until:
            msg = f"agreement {agreement.agreement_id} has expired"
            raise AgreementViolatedError(msg)
