"""Agent Card schema and route handler (``PROTOCOL_SPEC.md`` §4.1).

The Agent Card lives at ``/.well-known/agent.json`` and announces both A2A
core fields and the Polypact extension. We model it as a Pydantic schema so
adopters can build cards programmatically and so we can add fields additively
without breaking existing implementations.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

POLYPACT_VERSION: Literal["0.1"] = "0.1"
"""Polypact protocol version this implementation supports."""

SUPPORTED_CONFORMANCE_LEVELS: tuple[int, ...] = (1, 2, 3)
"""Conformance levels (PROTOCOL_SPEC.md §1.2). Phase 3 supports Levels 1-3."""


class PolypactExtension(BaseModel):
    """Polypact section of the Agent Card."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["0.1"] = POLYPACT_VERSION
    manifests_url: str = Field(..., description="Absolute URL of the manifest list endpoint.")
    supported_transfer_modes: list[str] = Field(default_factory=list)
    supported_conformance_levels: list[int] = Field(default_factory=list)
    extensions: list[str] = Field(
        default_factory=list,
        description="Reserved-namespace extensions advertised (e.g., 'knowledge:0.1-draft').",
    )


class AgentCard(BaseModel):
    """A2A-compatible Agent Card with Polypact extension.

    Only the fields Polypact actively reads or produces are modeled; A2A may
    define more. ``extra="allow"`` keeps the model forward-compatible with the
    A2A core spec.
    """

    model_config = ConfigDict(extra="allow")

    name: str
    description: str
    url: str = Field(..., description="Base URL where this agent is reachable.")
    polypact: PolypactExtension


def build_agent_card_router(card: AgentCard) -> APIRouter:
    """Build a router that serves ``card`` at ``/.well-known/agent.json``."""
    router = APIRouter()

    @router.get("/.well-known/agent.json")
    async def get_agent_card() -> AgentCard:
        return card

    return router
