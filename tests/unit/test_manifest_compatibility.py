"""Tests for composition-compatibility checks (PROTOCOL_SPEC.md §3.3)."""

from __future__ import annotations

import pytest

from polypact.manifest import (
    ComposeMode,
    DelegateMode,
    IOField,
    IOSpec,
    LeaseMode,
    Owner,
    SchemaRelations,
    SkillManifest,
    TeachMode,
    TransferModes,
    check_composition,
    check_parallel,
    check_sequential,
)


def _manifest(
    *,
    skill_id: str,
    inputs: list[IOField],
    outputs: list[IOField],
) -> SkillManifest:
    return SkillManifest(
        manifest_version="0.1",
        id=skill_id,
        name=skill_id.split("#", 1)[1],
        description="test fixture skill",
        owner=Owner(agent_id=skill_id.split("#", 1)[0]),
        version="1.0.0",
        io=IOSpec(inputs=inputs, outputs=outputs),
        transfer_modes=TransferModes(
            delegate=DelegateMode(supported=True),
            lease=LeaseMode(supported=False),
            teach=TeachMode(supported=False),
            compose=ComposeMode(supported=True, compose_modes=["sequential", "parallel"]),
        ),
    )


# --- Sequential ---


def test_sequential_compatible_when_media_type_and_schema_ref_match() -> None:
    a = _manifest(
        skill_id="did:web:a.com#step1",
        inputs=[IOField(name="x", media_type="text/plain")],
        outputs=[
            IOField(name="result", media_type="application/json", schema_ref="schema:Foo"),
        ],
    )
    b = _manifest(
        skill_id="did:web:b.com#step2",
        inputs=[
            IOField(name="payload", media_type="application/json", schema_ref="schema:Foo"),
        ],
        outputs=[IOField(name="ok", media_type="application/json")],
    )
    report = check_sequential(a, b)
    assert report.compatible
    assert len(report.matches) == 1
    assert report.matches[0].schema_ref_match
    assert report.matches[0].via_relation is False


def test_sequential_incompatible_when_media_types_differ() -> None:
    a = _manifest(
        skill_id="did:web:a.com#s1",
        inputs=[IOField(name="x", media_type="text/plain")],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    b = _manifest(
        skill_id="did:web:b.com#s2",
        inputs=[IOField(name="x", media_type="application/pdf")],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    report = check_sequential(a, b)
    assert not report.compatible
    assert "media_type" in report.reasons[0] or "schema_ref" in report.reasons[0]


def test_sequential_incompatible_when_schema_refs_differ() -> None:
    a = _manifest(
        skill_id="did:web:a.com#s1",
        inputs=[IOField(name="x", media_type="text/plain")],
        outputs=[
            IOField(name="r", media_type="application/json", schema_ref="schema:Foo"),
        ],
    )
    b = _manifest(
        skill_id="did:web:b.com#s2",
        inputs=[
            IOField(name="x", media_type="application/json", schema_ref="schema:Bar"),
        ],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    report = check_sequential(a, b)
    assert not report.compatible


def test_sequential_compatible_via_registered_relation() -> None:
    a = _manifest(
        skill_id="did:web:a.com#s1",
        inputs=[IOField(name="x", media_type="text/plain")],
        outputs=[
            IOField(name="r", media_type="application/json", schema_ref="schema:LegacyFoo"),
        ],
    )
    b = _manifest(
        skill_id="did:web:b.com#s2",
        inputs=[
            IOField(name="x", media_type="application/json", schema_ref="schema:Foo"),
        ],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    relations = SchemaRelations()
    relations.register("schema:LegacyFoo", "schema:Foo")
    report = check_sequential(a, b, relations)
    assert report.compatible
    assert report.matches[0].via_relation is True
    assert report.matches[0].schema_ref_match is False


def test_sequential_compatible_when_either_side_has_no_schema_ref() -> None:
    a = _manifest(
        skill_id="did:web:a.com#s1",
        inputs=[IOField(name="x", media_type="text/plain")],
        outputs=[IOField(name="r", media_type="application/json", schema_ref=None)],
    )
    b = _manifest(
        skill_id="did:web:b.com#s2",
        inputs=[IOField(name="x", media_type="application/json", schema_ref="schema:Foo")],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    report = check_sequential(a, b)
    assert report.compatible
    assert report.matches[0].via_relation is False


# --- Parallel ---


def test_parallel_compatible_when_required_inputs_match() -> None:
    a = _manifest(
        skill_id="did:web:a.com#p1",
        inputs=[IOField(name="payload", media_type="application/json", schema_ref="schema:X")],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    b = _manifest(
        skill_id="did:web:b.com#p2",
        inputs=[IOField(name="payload", media_type="application/json", schema_ref="schema:X")],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    report = check_parallel(a, b)
    assert report.compatible


def test_parallel_incompatible_when_input_names_differ() -> None:
    a = _manifest(
        skill_id="did:web:a.com#p1",
        inputs=[IOField(name="payload", media_type="application/json")],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    b = _manifest(
        skill_id="did:web:b.com#p2",
        inputs=[IOField(name="payload2", media_type="application/json")],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    report = check_parallel(a, b)
    assert not report.compatible


def test_parallel_optional_inputs_dont_block() -> None:
    a = _manifest(
        skill_id="did:web:a.com#p1",
        inputs=[
            IOField(name="x", media_type="application/json"),
            IOField(name="hint", media_type="text/plain", required=False),
        ],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    b = _manifest(
        skill_id="did:web:b.com#p2",
        inputs=[IOField(name="x", media_type="application/json")],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    report = check_parallel(a, b)
    assert report.compatible


# --- N-ary composition ---


def test_check_composition_sequential_three_steps() -> None:
    s1 = _manifest(
        skill_id="did:web:a.com#step1",
        inputs=[IOField(name="src", media_type="text/plain")],
        outputs=[IOField(name="mid", media_type="application/json", schema_ref="schema:M")],
    )
    s2 = _manifest(
        skill_id="did:web:b.com#step2",
        inputs=[IOField(name="mid", media_type="application/json", schema_ref="schema:M")],
        outputs=[IOField(name="result", media_type="application/json", schema_ref="schema:R")],
    )
    s3 = _manifest(
        skill_id="did:web:c.com#step3",
        inputs=[IOField(name="result", media_type="application/json", schema_ref="schema:R")],
        outputs=[IOField(name="final", media_type="application/json")],
    )
    report = check_composition([s1, s2, s3], "sequential")
    assert report.compatible
    assert len(report.matches) == 2


def test_check_composition_requires_at_least_two_manifests() -> None:
    s1 = _manifest(
        skill_id="did:web:a.com#solo",
        inputs=[IOField(name="x", media_type="text/plain")],
        outputs=[IOField(name="r", media_type="application/json")],
    )
    with pytest.raises(ValueError, match="at least two"):
        check_composition([s1], "sequential")
