"""Polypact server SDK: a FastAPI app factory.

Phase 1 exposed Level-1 discovery (Agent Card + manifest list/fetch). Phase 2
added Level-2: skill-handler registration and the ``polypact.task.invoke`` /
``polypact.discover.check_composition`` RPCs. Phase 3 adds Level-3 negotiation:
``polypact.negotiate.{propose,counter_propose,accept,reject}``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from fastapi import APIRouter, FastAPI

from polypact.discovery import (
    POLYPACT_VERSION,
    SUPPORTED_CONFORMANCE_LEVELS,
    AgentCard,
    PolypactExtension,
    build_agent_card_router,
    build_manifest_router,
)
from polypact.identity import AgentKeypair, build_did_document
from polypact.manifest import (
    ComposeKind,
    ManifestRegistry,
    SchemaRelations,
    SkillManifest,
    check_composition,
)
from polypact.negotiation import (
    AcceptRequest,
    CounterProposeRequest,
    InMemoryNegotiationStore,
    NegotiationCoordinator,
    NegotiationState,
    NegotiationStatus,
    NegotiationStore,
    ProposeRequest,
    RejectRequest,
)
from polypact.negotiation.fsm import now_utc
from polypact.transfer import (
    AgreementIndex,
    CheckCompositionRequest,
    ComposeRequest,
    DelegatePrimitive,
    Invoker,
    InvokeRequest,
    InvokeResult,
    LeasePrimitive,
    SkillHandler,
    TeachArtifact,
    TeachPrimitive,
    TeachRequest,
    synthesize_composite,
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
        negotiation_store: NegotiationStore | None = None,
        signing_key: AgentKeypair | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.base_url = base_url.rstrip("/")
        self.signing_key = signing_key
        self.registry = ManifestRegistry()
        for manifest in manifests:
            self.registry.register(manifest)
        self.schema_relations = schema_relations or SchemaRelations()
        self.dispatcher = Dispatcher()
        self.delegate = DelegatePrimitive(self.registry)
        self.negotiation_store: NegotiationStore = negotiation_store or InMemoryNegotiationStore()
        self.negotiations = NegotiationCoordinator(
            provider_agent_id=self.agent_id,
            manifests=self.registry,
            store=self.negotiation_store,
            signing_key=signing_key,
        )
        self.lease = LeasePrimitive(self.delegate)
        self.teach = TeachPrimitive()
        self.agreement_index = AgreementIndex(self.negotiation_store)
        self.invoker = Invoker(
            index=self.agreement_index,
            delegate=self.delegate,
            lease=self.lease,
        )
        self._wire_phase2_rpcs()
        self._wire_phase3_rpcs()
        self._wire_phase4_rpcs()

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
        if self.signing_key is not None:
            application.include_router(_build_did_router(self.signing_key))
        return application

    def register_teach_artifact(
        self,
        skill_id: str,
        artifact: TeachArtifact,
    ) -> None:
        """Register the artifact returned for ``polypact.transfer.teach`` calls."""
        # Validate the skill is published (raises UnknownSkillError if not).
        self.registry.get(skill_id)
        self.teach.register(skill_id, artifact)

    def _wire_phase2_rpcs(self) -> None:
        """Register the Phase 2 RPC handlers on the dispatcher."""

        async def task_invoke(params: dict[str, Any]) -> dict[str, Any]:
            request = InvokeRequest.model_validate(params)
            if request.agreement_id is not None:
                record, agreement = self.agreement_index.find(request.agreement_id)
                output = await self.invoker.invoke(
                    agreement_record=record,
                    agreement=agreement,
                    caller=request.agent_id,
                    payload=request.input,
                    now=now_utc(),
                )
                return InvokeResult(skill_id=agreement.skill_id, output=output).model_dump()
            assert request.skill_id is not None  # validator guarantees this
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

    def _wire_phase3_rpcs(self) -> None:
        """Register the Phase 3 negotiation RPC handlers."""

        async def negotiate_propose(params: dict[str, Any]) -> dict[str, Any]:
            request = ProposeRequest.model_validate(params)
            record = self.negotiations.propose(request)
            return NegotiationStatus(
                negotiation_id=record.negotiation_id,
                state=record.state,
                expires_at=record.expires_at,
            ).model_dump(mode="json")

        async def negotiate_counter_propose(params: dict[str, Any]) -> dict[str, Any]:
            request = CounterProposeRequest.model_validate(params)
            record = self.negotiations.counter_propose(request)
            return NegotiationStatus(
                negotiation_id=record.negotiation_id,
                state=record.state,
                expires_at=record.expires_at,
            ).model_dump(mode="json")

        async def negotiate_accept(params: dict[str, Any]) -> dict[str, Any]:
            request = AcceptRequest.model_validate(params)
            record = self.negotiations.accept(request)
            assert record.state == NegotiationState.AGREED
            assert record.agreement is not None
            return record.agreement.model_dump(mode="json")

        async def negotiate_reject(params: dict[str, Any]) -> dict[str, Any]:
            request = RejectRequest.model_validate(params)
            record = self.negotiations.reject(request)
            return NegotiationStatus(
                negotiation_id=record.negotiation_id,
                state=record.state,
                expires_at=record.expires_at,
                rejection_reason=record.rejection_reason,
            ).model_dump(mode="json")

        self.dispatcher.register("polypact.negotiate.propose", negotiate_propose)
        self.dispatcher.register(
            "polypact.negotiate.counter_propose",
            negotiate_counter_propose,
        )
        self.dispatcher.register("polypact.negotiate.accept", negotiate_accept)
        self.dispatcher.register("polypact.negotiate.reject", negotiate_reject)

    def _wire_phase4_rpcs(self) -> None:
        """Register the Phase 4 transfer-mode RPC handlers."""

        async def transfer_teach(params: dict[str, Any]) -> dict[str, Any]:
            request = TeachRequest.model_validate(params)
            record, agreement = self.agreement_index.find(request.agreement_id)
            self.agreement_index.assert_caller_is_party(record, request.agent_id)
            self.agreement_index.assert_within_validity_window(agreement, now=now_utc())
            return self.teach.transfer(agreement).model_dump()

        async def transfer_compose(params: dict[str, Any]) -> dict[str, Any]:
            request = ComposeRequest.model_validate(params)
            record, agreement = self.agreement_index.find(request.agreement_id)
            self.agreement_index.assert_caller_is_party(record, request.agent_id)
            self.agreement_index.assert_within_validity_window(agreement, now=now_utc())
            composite = synthesize_composite(
                agreement=agreement,
                manifests=self.registry,
                relations=self.schema_relations,
            )
            return composite.model_dump(mode="json")

        self.dispatcher.register("polypact.transfer.teach", transfer_teach)
        self.dispatcher.register("polypact.transfer.compose", transfer_compose)


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


def _build_did_router(keypair: AgentKeypair) -> APIRouter:
    """Serve the agent's DID document at ``/.well-known/did.json``."""
    router = APIRouter()
    document = build_did_document(
        did=keypair.did,
        key_id=keypair.key_id,
        public_key_b64=keypair.public_key_b64(),
    )

    @router.get("/.well-known/did.json")
    async def get_did_document() -> dict[str, Any]:
        return document

    return router
