"""Storage for negotiation records.

Defines a :class:`NegotiationStore` Protocol so persistence backends can swap
in without disturbing the FSM or coordinator. The in-memory implementation
ships in v0.1; Postgres/Redis are deferred per ``FUTURE_WORK.md`` §5.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from polypact.negotiation.schemas import NegotiationRecord


class UnknownNegotiationError(KeyError):
    """No negotiation with the given ID exists in the store."""


class NegotiationStore(Protocol):
    """Read/write interface for any negotiation storage backend."""

    def put(self, record: NegotiationRecord) -> None:
        """Insert or replace ``record`` keyed by ``record.negotiation_id``."""
        ...

    def get(self, negotiation_id: UUID) -> NegotiationRecord:
        """Return a single record. Raises :class:`UnknownNegotiationError` if absent."""
        ...

    def list(self) -> list[NegotiationRecord]:
        """Return all records. Order is implementation-defined."""
        ...


class InMemoryNegotiationStore:
    """Process-local :class:`NegotiationStore`.

    Records are stored by reference; callers should treat
    :class:`NegotiationRecord` instances as immutable (the FSM produces new
    records via ``model_copy``). The coordinator handles all mutation through
    full record replacement.
    """

    def __init__(self) -> None:
        self._records: dict[UUID, NegotiationRecord] = {}

    def put(self, record: NegotiationRecord) -> None:
        """Insert or replace ``record`` keyed by ``record.negotiation_id``."""
        self._records[record.negotiation_id] = record

    def get(self, negotiation_id: UUID) -> NegotiationRecord:
        """Return a single record. Raises :class:`UnknownNegotiationError` if absent."""
        try:
            return self._records[negotiation_id]
        except KeyError as exc:
            msg = f"unknown negotiation: {negotiation_id}"
            raise UnknownNegotiationError(msg) from exc

    def list(self) -> list[NegotiationRecord]:
        """Return all records (insertion order)."""
        return list(self._records.values())

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, negotiation_id: object) -> bool:
        return isinstance(negotiation_id, UUID) and negotiation_id in self._records
