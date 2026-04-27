"""Polypact server SDK: a FastAPI app factory.

In Phase 1 the server exposes Level-1 discovery: Agent Card + manifest list/fetch.
A JSON-RPC dispatcher is mounted at ``/polypact/v1/rpc`` with no methods
registered yet; later phases (negotiation, task invocation, transfer) will
register handlers via :meth:`PolypactServer.register_method`.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import FastAPI

from polypact.discovery import (
    POLYPACT_VERSION,
    SUPPORTED_CONFORMANCE_LEVELS,
    AgentCard,
    PolypactExtension,
    build_agent_card_router,
    build_manifest_router,
)
from polypact.manifest import ManifestRegistry, SkillManifest
from polypact.transport import Dispatcher, Handler, build_rpc_router


class PolypactServer:
    """Holds protocol state (registry, dispatcher) and produces a FastAPI app.

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
    ) -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.base_url = base_url.rstrip("/")
        self.registry = ManifestRegistry()
        for manifest in manifests:
            self.registry.register(manifest)
        self.dispatcher = Dispatcher()

    def register_method(self, method: str, handler: Handler) -> None:
        """Register a JSON-RPC handler. Wraps :meth:`Dispatcher.register`."""
        self.dispatcher.register(method, handler)

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
