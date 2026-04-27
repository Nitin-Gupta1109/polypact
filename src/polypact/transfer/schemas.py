"""Wire schemas for transfer-mode RPCs.

In Phase 2 only ``polypact.task.invoke`` is implemented (delegate mode). The
spec (``PROTOCOL_SPEC.md`` §6.1) describes invoke params as
``{agreement_id, input}`` — but agreements don't exist until Phase 3 (the
negotiation FSM). Until then, ``InvokeRequest`` carries ``skill_id`` directly.

When Phase 3 lands, ``agreement_id`` is added to the same envelope and gates
the call against negotiated terms. The ``skill_id``-only form remains valid
for ``delegate`` mode (which is "no state retained" per §6.1) but not for
``lease``, ``teach``, or ``compose``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InvokeRequest(BaseModel):
    """Params block for ``polypact.task.invoke``.

    Phase 4 made the request agreement-gated: callers SHOULD pass
    ``agreement_id`` to invoke against an accepted agreement. The
    ``skill_id``-only form remains valid as the §6.1 baseline (delegate mode,
    "no state retained") and is the path Phase 2 tests still take. Lease
    invocations require ``agreement_id``.
    """

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Caller's DID, per ``PROTOCOL_SPEC.md`` §2.2.")
    trace_id: str = Field(..., description="UUID for correlating logs across the call.")
    agreement_id: UUID | None = Field(default=None, description="Accepted agreement.")
    skill_id: str | None = Field(
        default=None,
        description="Direct skill ID — only valid for delegate-mode baseline.",
    )
    input: dict[str, Any] = Field(..., description="Skill-specific input payload.")

    @model_validator(mode="after")
    def _exactly_one_target(self) -> InvokeRequest:
        if (self.agreement_id is None) == (self.skill_id is None):
            msg = "InvokeRequest requires exactly one of agreement_id or skill_id"
            raise ValueError(msg)
        return self


class TeachRequest(BaseModel):
    """Params block for ``polypact.transfer.teach`` (PROTOCOL_SPEC.md §6.3)."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    trace_id: str
    agreement_id: UUID


class ComposeRequest(BaseModel):
    """Params block for ``polypact.transfer.compose`` (PROTOCOL_SPEC.md §6.4)."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    trace_id: str
    agreement_id: UUID


class InvokeResult(BaseModel):
    """Result block returned by ``polypact.task.invoke``."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str
    output: dict[str, Any]


class CheckCompositionRequest(BaseModel):
    """Params block for ``polypact.discover.check_composition`` (PROTOCOL_SPEC.md §3.3).

    The spec doesn't fix the wire shape; we accept a list of skill IDs (all
    expected to live on the receiving agent) and a compose mode.
    """

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    trace_id: str
    skill_ids: list[str] = Field(..., min_length=2)
    mode: str = Field(..., description="'sequential' or 'parallel'.")
