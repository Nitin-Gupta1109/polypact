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

from pydantic import BaseModel, ConfigDict, Field


class InvokeRequest(BaseModel):
    """Params block for ``polypact.task.invoke`` (Phase 2 form)."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Caller's DID, per ``PROTOCOL_SPEC.md`` §2.2.")
    trace_id: str = Field(..., description="UUID for correlating logs across the call.")
    skill_id: str = Field(..., description="DID-with-fragment ID of the skill being invoked.")
    input: dict[str, Any] = Field(..., description="Skill-specific input payload.")


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
