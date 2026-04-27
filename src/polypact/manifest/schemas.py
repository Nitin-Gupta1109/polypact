"""Pydantic models for the Skill Manifest (``PROTOCOL_SPEC.md`` §3.1).

The manifest is the canonical description of a skill: identity, I/O typing,
supported transfer modes, and offered terms. Every field here corresponds 1:1
to a field in the spec; deviations are flagged in ``DESIGN_NOTES.md``.

Models use ``extra="forbid"`` to surface typos and unrecognized fields at parse
time. Free-form areas (``metadata``, ``terms.pricing.model``) intentionally
allow any value.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_MANIFEST_VERSIONS: tuple[str, ...] = ("0.1",)
"""Manifest schema versions this implementation can parse and produce."""

_DID_SKILL_ID_RE = re.compile(
    r"^did:[a-z0-9]+:[a-zA-Z0-9._:%-]+#[a-zA-Z0-9._\-/]+$",
)
"""Skill IDs are DIDs with a fragment naming the skill (``PROTOCOL_SPEC.md`` §3.2)."""


class _StrictBase(BaseModel):
    """Shared config for protocol models: forbid extras, validate on assignment."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, frozen=False)


class Owner(_StrictBase):
    """The agent that owns and serves a skill."""

    agent_id: str = Field(..., description="DID of the owning agent (e.g., did:web:...).")
    display_name: str | None = Field(default=None, description="Human-readable agent name.")


class IOField(_StrictBase):
    """A single typed slot on a skill's input or output side."""

    name: str = Field(..., min_length=1)
    media_type: str = Field(..., description="IANA media type (e.g., application/pdf).")
    schema_ref: str | None = Field(
        default=None,
        description="URI of a JSON Schema or schema.org type describing the payload.",
    )
    required: bool = Field(default=True)


class IOSpec(_StrictBase):
    """The complete I/O surface of a skill."""

    inputs: list[IOField] = Field(..., min_length=1)
    outputs: list[IOField] = Field(..., min_length=1)


class DelegateMode(_StrictBase):
    """Configuration for ``delegate`` transfer mode (``PROTOCOL_SPEC.md`` §6.1)."""

    supported: bool


class LeaseMode(_StrictBase):
    """Configuration for ``lease`` transfer mode (``PROTOCOL_SPEC.md`` §6.2)."""

    supported: bool
    max_invocations: int | None = Field(default=None, ge=1)
    max_ttl_seconds: int | None = Field(default=None, ge=1)


class TeachMode(_StrictBase):
    """Configuration for ``teach`` transfer mode (``PROTOCOL_SPEC.md`` §6.3)."""

    supported: bool
    reason: str | None = Field(
        default=None,
        description="Optional rationale when not supported (e.g., 'proprietary').",
    )


ComposeKind = Literal["sequential", "parallel"]


class ComposeMode(_StrictBase):
    """Configuration for ``compose`` transfer mode (``PROTOCOL_SPEC.md`` §6.4)."""

    supported: bool
    compose_modes: list[ComposeKind] = Field(default_factory=list)


class TransferModes(_StrictBase):
    """The four transfer-mode declarations carried on every manifest.

    Per ``PROTOCOL_SPEC.md`` §3.2, at least one mode must have ``supported=True``;
    that rule lives in :mod:`polypact.manifest.validation` (not enforced at the
    schema layer because it spans sibling fields).
    """

    delegate: DelegateMode
    lease: LeaseMode
    teach: TeachMode
    compose: ComposeMode


class Pricing(_StrictBase):
    """Pricing terms. ``model`` is intentionally free-form for v0.1."""

    model: str = Field(..., description="e.g., 'free', 'per_invocation', 'subscription'.")
    amount: float | None = Field(default=None, ge=0.0)
    currency: str | None = Field(
        default=None,
        description="ISO 4217 currency code (uppercase).",
        pattern=r"^[A-Z]{3}$",
    )


class DataHandling(_StrictBase):
    """Data-handling commitments: retention, locality, sub-processor policy."""

    retention_seconds: int = Field(default=0, ge=0)
    processing_locations: list[str] = Field(default_factory=list)
    subprocessors_allowed: bool = False


class SLA(_StrictBase):
    """Service-level expectations published by the provider."""

    p50_latency_ms: int | None = Field(default=None, ge=0)
    p99_latency_ms: int | None = Field(default=None, ge=0)
    availability: float | None = Field(default=None, ge=0.0, le=1.0)


class Terms(_StrictBase):
    """The full terms block negotiated against during the §5 FSM."""

    pricing: Pricing | None = None
    data_handling: DataHandling | None = None
    sla: SLA | None = None


class SkillManifest(_StrictBase):
    """Top-level Skill Manifest (``PROTOCOL_SPEC.md`` §3.1).

    Schema-level constraints live here; cross-field rules (e.g., DID format,
    "at least one transfer mode supported") live in
    :mod:`polypact.manifest.validation` so they can be invoked deliberately and
    raise :class:`~polypact.errors.ManifestValidationError`.
    """

    manifest_version: Literal["0.1"]
    id: str = Field(..., description="DID-with-fragment skill identifier.")
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    owner: Owner
    version: str = Field(..., description="Skill version (recommend semver).")
    io: IOSpec
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    transfer_modes: TransferModes
    terms: Terms = Field(default_factory=Terms)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_skill_id(cls, value: str) -> str:
        """Ensure the skill ID is a DID with a fragment.

        Examples of valid IDs::

            did:web:example.com#extract-invoice
            did:key:z6Mk...#step1
        """
        if not _DID_SKILL_ID_RE.match(value):
            msg = f"skill id must be a DID with a fragment naming the skill, got {value!r}"
            raise ValueError(msg)
        return value
