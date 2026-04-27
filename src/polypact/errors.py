"""Domain error hierarchy for Polypact.

All Polypact-specific exceptions inherit from :class:`PolypactError`. Each error
maps to a JSON-RPC 2.0 error code per ``PROTOCOL_SPEC.md`` §2.3. The mapping
itself lives in :mod:`polypact.transport.errors` to keep this module free of
transport concerns.
"""

from __future__ import annotations


class PolypactError(Exception):
    """Base class for all Polypact domain errors.

    Subclasses define a class-level ``code`` matching the JSON-RPC error code
    they map to. This allows transport-layer dispatchers to translate them
    uniformly without per-exception ``isinstance`` chains.
    """

    code: int = -32000
    """JSON-RPC error code. Subclasses override per ``PROTOCOL_SPEC.md`` §2.3."""

    def __init__(self, message: str, *, data: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.data = data


class UnknownSkillError(PolypactError):
    """A referenced skill ID does not exist in the provider's manifest registry."""

    code = -32001


class NegotiationStateError(PolypactError):
    """An attempted FSM transition is invalid for the current negotiation state."""

    code = -32002


class AgreementViolatedError(PolypactError):
    """An invocation violates the terms of an agreement (e.g., lease exhausted)."""

    code = -32003


class CapabilityMismatchError(PolypactError):
    """Composition I/O types are incompatible (see ``PROTOCOL_SPEC.md`` §3.3)."""

    code = -32004


class AuthorizationFailedError(PolypactError):
    """The caller is not authorized for the requested operation."""

    code = -32005


class ManifestValidationError(PolypactError):
    """A skill manifest fails beyond-schema validation (``PROTOCOL_SPEC.md`` §3.2).

    Distinct from Pydantic ``ValidationError`` (schema-level). Mapped to the
    generic Polypact error code; transport surfaces it as ``-32000``.
    """

    code = -32000
