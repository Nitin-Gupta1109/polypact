"""The ``compose`` transfer primitive (``PROTOCOL_SPEC.md`` §6.4).

Two or more skills are exposed as a chained pipeline. The provider returns a
synthesized composite manifest that the initiator can invoke as a normal
skill. Type-checking is performed at composition time per §3.3.

Phase 4 implements composition compatibility checking and synthesizes the
composite manifest. Actual *execution* of a composition (orchestrating the
underlying invocations) is a higher-level orchestration concern beyond v0.1.
"""

from __future__ import annotations

from polypact.errors import (
    AgreementViolatedError,
    CapabilityMismatchError,
    UnknownSkillError,
)
from polypact.manifest import (
    ComposeKind,
    IOSpec,
    ManifestStore,
    Owner,
    SchemaRelations,
    SkillManifest,
    check_composition,
)
from polypact.negotiation import Agreement


def synthesize_composite(
    *,
    agreement: Agreement,
    manifests: ManifestStore,
    relations: SchemaRelations | None = None,
) -> SkillManifest:
    """Build a composite :class:`SkillManifest` from an accepted compose agreement.

    Reads ``agreement.terms.compose.steps`` (the agreed pipeline) and
    ``agreement.terms.compose.compose_kind`` (sequential vs parallel). Type-
    checks the composition; raises :class:`CapabilityMismatchError` (-32004)
    on incompatibility per §6.4.
    """
    if agreement.transfer_mode != "compose":
        msg = (
            f"agreement {agreement.agreement_id} is for mode "
            f"{agreement.transfer_mode!r}, not 'compose'"
        )
        raise AgreementViolatedError(msg)
    compose_terms = agreement.terms.compose
    if compose_terms is None:
        msg = f"agreement {agreement.agreement_id} has no compose terms"
        raise AgreementViolatedError(msg)
    step_manifests = [_lookup_manifest(manifests, sid) for sid in compose_terms.steps]
    mode: ComposeKind = compose_terms.compose_kind
    report = check_composition(step_manifests, mode, relations)
    if not report.compatible:
        reasons = "; ".join(report.reasons) or "incompatible"
        msg = f"composition I/O types incompatible: {reasons}"
        raise CapabilityMismatchError(msg)
    return _build_composite_manifest(agreement, step_manifests, mode)


def _lookup_manifest(store: ManifestStore, skill_id: str) -> SkillManifest:
    try:
        return store.get(skill_id)
    except UnknownSkillError as exc:
        msg = f"composition references unknown skill: {skill_id!r}"
        raise UnknownSkillError(msg) from exc


def _build_composite_manifest(
    agreement: Agreement,
    steps: list[SkillManifest],
    mode: ComposeKind,
) -> SkillManifest:
    """Synthesize a SkillManifest representing the composite pipeline.

    For sequential pipelines, inputs come from the first step and outputs from
    the last. For parallel pipelines, inputs from any step (they should all
    match by construction; we use the first) and outputs are the union of all
    step outputs.
    """
    if mode == "sequential":
        inputs = steps[0].io.inputs
        outputs = steps[-1].io.outputs
    else:  # parallel
        inputs = steps[0].io.inputs
        seen: set[tuple[str, str]] = set()
        outputs = []
        for step in steps:
            for field in step.io.outputs:
                key = (field.name, field.media_type)
                if key in seen:
                    continue
                seen.add(key)
                outputs.append(field)
    composite_id = f"{agreement.parties.provider}#composite-{agreement.agreement_id.hex[:8]}"
    return SkillManifest(
        manifest_version="0.1",
        id=composite_id,
        name=f"Composite ({mode}) of {len(steps)} skills",
        description=(
            f"Synthesized composite manifest for agreement {agreement.agreement_id} "
            f"chaining {[s.id for s in steps]} as {mode}."
        ),
        owner=Owner(agent_id=agreement.parties.provider),
        version="0.1.0",
        io=IOSpec(inputs=inputs, outputs=outputs),
        transfer_modes=steps[0].transfer_modes,
        terms=steps[0].terms,
    )
