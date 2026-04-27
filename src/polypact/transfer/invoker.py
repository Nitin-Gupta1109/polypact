"""Routes ``polypact.task.invoke`` to the correct primitive given an agreement.

Per ``PROTOCOL_SPEC.md`` §6, ``delegate`` and ``lease`` agreements can be
invoked via ``polypact.task.invoke``. ``teach`` and ``compose`` use their own
RPC methods (``polypact.transfer.teach`` / ``polypact.transfer.compose``)
and aren't dispatched through here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from polypact.errors import AgreementViolatedError, AuthorizationFailedError
from polypact.negotiation import Agreement, NegotiationRecord
from polypact.transfer.agreement_index import AgreementIndex
from polypact.transfer.delegate import DelegatePrimitive
from polypact.transfer.lease import LeasePrimitive


class Invoker:
    """Routes invoke RPCs to the right primitive based on the agreement.

    Glues :class:`AgreementIndex`, :class:`DelegatePrimitive`, and
    :class:`LeasePrimitive` together for the wire-level invoke RPC.
    """

    def __init__(
        self,
        *,
        index: AgreementIndex,
        delegate: DelegatePrimitive,
        lease: LeasePrimitive,
    ) -> None:
        self._index = index
        self._delegate = delegate
        self._lease = lease

    async def invoke(
        self,
        *,
        agreement_record: NegotiationRecord,
        agreement: Agreement,
        caller: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        """Route the invocation to the correct primitive.

        The caller is expected to have already resolved ``agreement_record``
        and ``agreement`` from the index; we double-check authorization and
        the validity window here so a single mistake at the call site can't
        leak through.
        """
        self._index.assert_caller_is_party(agreement_record, caller)
        self._index.assert_within_validity_window(agreement, now=now)
        if agreement.transfer_mode == "delegate":
            return await self._delegate.invoke(agreement.skill_id, payload)
        if agreement.transfer_mode == "lease":
            return await self._lease.invoke(agreement, payload, now=now)
        if agreement.transfer_mode in ("teach", "compose"):
            msg = (
                f"agreement {agreement.agreement_id} uses transfer_mode "
                f"{agreement.transfer_mode!r}; use polypact.transfer.{agreement.transfer_mode}"
            )
            raise AgreementViolatedError(msg)
        msg = f"unknown transfer_mode {agreement.transfer_mode!r}"
        raise AuthorizationFailedError(msg)
