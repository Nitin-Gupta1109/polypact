"""The ``delegate`` transfer primitive (``PROTOCOL_SPEC.md`` §6.1).

Delegate is the baseline: provider executes the skill on the initiator's
input and returns the output. No state retained between calls.

This module owns the in-process registry mapping skill IDs to handler
callables. A handler is an async function ``(input: dict) -> dict``. The
:class:`DelegatePrimitive` enforces that a handler exists for the requested
skill ID and that the skill ID is recognized by the manifest registry (so
you can't expose a handler for a skill you haven't published).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from polypact.errors import UnknownSkillError
from polypact.manifest import ManifestStore

SkillHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
"""An async skill handler: takes an input dict, returns an output dict."""


class DelegatePrimitive:
    """In-process implementation of the delegate primitive.

    Holds the skill_id → handler map. ``invoke`` looks up the handler and
    calls it; if the skill is not in the manifest store or has no registered
    handler, raises :class:`UnknownSkillError`.
    """

    def __init__(self, manifest_store: ManifestStore) -> None:
        self._manifests = manifest_store
        self._handlers: dict[str, SkillHandler] = {}

    def register(self, skill_id: str, handler: SkillHandler) -> None:
        """Register ``handler`` to serve invocations of ``skill_id``.

        Raises:
            UnknownSkillError: If no manifest with this ID is in the store.
            ValueError: If a handler is already registered for this skill.
        """
        # Ensure the skill is published; raises UnknownSkillError if not.
        self._manifests.get(skill_id)
        if skill_id in self._handlers:
            msg = f"handler for {skill_id!r} is already registered"
            raise ValueError(msg)
        self._handlers[skill_id] = handler

    def has_handler(self, skill_id: str) -> bool:
        """Return True if a handler is registered for ``skill_id``."""
        return skill_id in self._handlers

    async def invoke(self, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke the registered handler for ``skill_id`` with ``payload``."""
        # Validates the manifest exists.
        self._manifests.get(skill_id)
        handler = self._handlers.get(skill_id)
        if handler is None:
            msg = f"no handler registered for skill {skill_id!r}"
            raise UnknownSkillError(msg)
        return await handler(payload)
