"""The ``lease`` transfer primitive (``PROTOCOL_SPEC.md`` §6.2).

Provider grants the initiator the right to invoke the skill up to
``max_invocations`` times within ``ttl_seconds``. State per agreement:
``invocations_used`` and the inherited ``valid_until`` from the agreement.

Lease state is tracked in a small in-memory store keyed by ``agreement_id``.
The primitive enforces the invocation cap and the validity window before
delegating to the registered skill handler.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from polypact.errors import AgreementViolatedError
from polypact.negotiation import Agreement
from polypact.transfer.delegate import DelegatePrimitive


class LeaseState(BaseModel):
    """Per-agreement lease state."""

    model_config = ConfigDict(extra="forbid")

    agreement_id: UUID
    max_invocations: int
    invocations_used: int = 0

    @property
    def invocations_remaining(self) -> int:
        """How many more invocations the lease still permits."""
        return max(0, self.max_invocations - self.invocations_used)


class LeasePrimitive:
    """Owns lease state and routes lease invocations through the delegate handler.

    Setup is implicit: on first invocation against an agreement, the lease
    state is created from the agreement's terms. Teardown is implicit too;
    expired or exhausted leases stay in the store as audit records but
    refuse further invocations.
    """

    def __init__(self, delegate: DelegatePrimitive) -> None:
        self._delegate = delegate
        self._states: dict[UUID, LeaseState] = {}

    def state_for(self, agreement_id: UUID) -> LeaseState | None:
        """Inspect lease state without mutating it."""
        return self._states.get(agreement_id)

    async def invoke(
        self,
        agreement: Agreement,
        payload: dict[str, Any],
        *,
        now: datetime,
    ) -> dict[str, Any]:
        """Invoke ``agreement``'s skill, decrementing the lease budget."""
        if agreement.terms.lease is None:
            msg = f"agreement {agreement.agreement_id} has no lease terms"
            raise AgreementViolatedError(msg)
        if now > agreement.valid_until:
            msg = f"lease {agreement.agreement_id} expired at {agreement.valid_until}"
            raise AgreementViolatedError(msg)
        state = self._states.setdefault(
            agreement.agreement_id,
            LeaseState(
                agreement_id=agreement.agreement_id,
                max_invocations=agreement.terms.lease.max_invocations,
            ),
        )
        if state.invocations_remaining <= 0:
            msg = (
                f"lease {agreement.agreement_id} exhausted "
                f"({state.invocations_used}/{state.max_invocations})"
            )
            raise AgreementViolatedError(msg)
        # Reserve the slot before invoking — even if the handler raises, the
        # caller used a budget unit per §6.2 ("invocations_used" is monotonic).
        state.invocations_used += 1
        return await self._delegate.invoke(agreement.skill_id, payload)
