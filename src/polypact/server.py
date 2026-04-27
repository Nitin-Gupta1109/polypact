"""Polypact server SDK: a FastAPI app factory.

Phase 1 exposed Level-1 discovery (Agent Card + manifest list/fetch). Phase 2
adds Conformance Level 2: skill-handler registration and the
``polypact.task.invoke`` and ``polypact.discover.check_composition`` RPCs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from fastapi import FastAPI

from polypact.discovery import (
    POLYPACT_VERSION,
    SUPPORTED_CONFORMANCE_LEVELS,
    AgentCard,
    PolypactExtension,
    build_agent_card_router,
    build_manifest_router,
)
from polypact.manifest import (
    ComposeKind,
    ManifestRegistry,
    SchemaRelations,
    SkillManifest,
    check_composition,
)
from polypact.transfer import (
    CheckCompositionRequest,
    DelegatePrimitive,
    InvokeRequest,
    InvokeResult,
    SkillHandler,
)
from polypact.transport import Dispatcher, Handler, build_rpc_router


class PolypactServer:
    """Holds protocol state (registry, dispatcher, primitives) and produces a FastAPI app.

    A single :class:`PolypactServer` instance corresponds to one agent
    identity. Use :meth:`app` to obtain the runnable :class:`FastAPI`.
    """

    def __init__(
        self,
        *,
        agent_id: str,
        agent_name: str,
        agent_description: str,
        base_url: str,
        manifests: Iterable[SkillManifest] = (),
        schema_relations: SchemaRelations | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.base_url = base_url.rstrip("/")
        self.registry = ManifestRegistry()
        for manifest in manifests:
            self.registry.register(manifest)
        self.schema_relations = schema_relations or SchemaRelations()
        self.dispatcher = Dispatcher()
        self.delegate = DelegatePrimitive(self.registry)
        self._wire_phase2_rpcs()

    def register_method(self, method: str, handler: Handler) -> None:
        """Register a JSON-RPC handler. Wraps :meth:`Dispatcher.register`."""
        self.dispatcher.register(method, handler)

    def register_skill(self, skill_id: str, handler: SkillHandler) -> None:
        """Register a skill handler for ``delegate``-mode invocations."""
        self.delegate.register(skill_id, handler)

    def skill(self, skill_id: str) -> Callable[[SkillHandler], SkillHandler]:
        """Decorator form of :meth:`register_skill`.

        Example::

            @server.skill("did:web:me.com#extract-invoice")
            async def extract_invoice(payload: dict) -> dict:
                ...
        """

        def decorator(handler: SkillHandler) -> SkillHandler:
            self.register_skill(skill_id, handler)
            return handler

        return decorator

    def agent_card(self) -> AgentCard:
        """Return the Agent Card this server will publish."""
        supported_modes = _supported_transfer_modes(self.registry.list())
        return AgentCard(
            name=self.agent_name,
            description=self.agent_description,
            url=self.base_url,
            polypact=PolypactExtension(
                version=POLYPACT_VERSION,
                manifests_url=f"{self.base_url}/polypact/v1/manifests",
                supported_transfer_modes=supported_modes,
                supported_conformance_levels=list(SUPPORTED_CONFORMANCE_LEVELS),
            ),
        )

    def app(self) -> FastAPI:
        """Build and return the FastAPI application for this server."""
        application = FastAPI(title=self.agent_name, description=self.agent_description)
        application.include_router(build_agent_card_router(self.agent_card()))
        application.include_router(build_manifest_router(self.registry))
        application.include_router(build_rpc_router(self.dispatcher))
        return application

    def _wire_phase2_rpcs(self) -> None:
        """Register the Phase 2 RPC handlers on the dispatcher."""

        async def task_invoke(params: dict[str, Any]) -> dict[str, Any]:
            request = InvokeRequest.model_validate(params)
            output = await self.delegate.invoke(request.skill_id, request.input)
            return InvokeResult(skill_id=request.skill_id, output=output).model_dump()

        async def discover_check_composition(params: dict[str, Any]) -> dict[str, Any]:
            request = CheckCompositionRequest.model_validate(params)
            mode: ComposeKind = _validate_compose_mode(request.mode)
            manifests = [self.registry.get(sid) for sid in request.skill_ids]
            report = check_composition(manifests, mode, self.schema_relations)
            return report.model_dump()

        self.dispatcher.register("polypact.task.invoke", task_invoke)
        self.dispatcher.register(
            "polypact.discover.check_composition",
            discover_check_composition,
        )


def create_app(
    *,
    agent_id: str,
    agent_name: str,
    agent_description: str,
    base_url: str,
    manifests: Iterable[SkillManifest] = (),
) -> FastAPI:
    """Convenience factory: build a :class:`PolypactServer` and return its app."""
    server = PolypactServer(
        agent_id=agent_id,
        agent_name=agent_name,
        agent_description=agent_description,
        base_url=base_url,
        manifests=manifests,
    )
    return server.app()


def _supported_transfer_modes(manifests: list[SkillManifest]) -> list[str]:
    """Aggregate supported transfer modes across all registered manifests."""
    modes: list[str] = []
    for name in ("delegate", "lease", "teach", "compose"):
        for manifest in manifests:
            mode = getattr(manifest.transfer_modes, name)
            if mode.supported:
                modes.append(name)
                break
    return modes


def _validate_compose_mode(mode: str) -> ComposeKind:
    """Narrow a wire string to the ``ComposeKind`` literal type."""
    if mode not in ("sequential", "parallel"):
        msg = f"unknown compose mode: {mode!r}"
        raise ValueError(msg)
    return mode  # type: ignore[return-value]
