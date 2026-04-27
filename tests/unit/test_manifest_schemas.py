"""Schema-level tests for SkillManifest and friends."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from polypact.manifest import IOField, IOSpec, Pricing, SkillManifest


def test_sample_manifest_round_trips_through_json(sample_manifest: SkillManifest) -> None:
    payload = sample_manifest.model_dump_json()
    restored = SkillManifest.model_validate_json(payload)
    assert restored == sample_manifest


def test_skill_id_must_be_did_with_fragment(sample_manifest: SkillManifest) -> None:
    bad_ids = [
        "extract-invoice",
        "https://example.com/skill",
        "did:web:example.com",
        "did:web:example.com#",
    ]
    for bad_id in bad_ids:
        with pytest.raises(ValidationError):
            sample_manifest.model_copy(update={"id": bad_id}).model_validate(
                sample_manifest.model_dump() | {"id": bad_id},
            )


def test_skill_id_accepts_did_web_and_did_key() -> None:
    SkillManifest.model_validate(
        _payload(skill_id="did:web:example.com#do-thing"),
    )
    SkillManifest.model_validate(
        _payload(skill_id="did:key:z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH#step1"),
    )


def test_io_must_have_at_least_one_input_and_output() -> None:
    with pytest.raises(ValidationError):
        IOSpec(inputs=[], outputs=[IOField(name="x", media_type="application/json")])
    with pytest.raises(ValidationError):
        IOSpec(inputs=[IOField(name="x", media_type="application/json")], outputs=[])


def test_extra_fields_are_rejected() -> None:
    payload = _payload()
    payload["surprise"] = "rejected"
    with pytest.raises(ValidationError):
        SkillManifest.model_validate(payload)


def test_currency_must_be_three_uppercase_letters() -> None:
    with pytest.raises(ValidationError):
        Pricing(model="per_invocation", amount=1.0, currency="usd")
    with pytest.raises(ValidationError):
        Pricing(model="per_invocation", amount=1.0, currency="DOLLARS")
    Pricing(model="per_invocation", amount=1.0, currency="USD")


def test_unsupported_manifest_version_is_rejected_at_schema_level() -> None:
    payload = _payload()
    payload["manifest_version"] = "9.9"
    with pytest.raises(ValidationError):
        SkillManifest.model_validate(payload)


def test_terms_default_to_empty_block(sample_manifest: SkillManifest) -> None:
    payload = sample_manifest.model_dump()
    payload.pop("terms")
    restored = SkillManifest.model_validate(payload)
    assert restored.terms.pricing is None
    assert restored.terms.data_handling is None
    assert restored.terms.sla is None


def _payload(*, skill_id: str = "did:web:example.com#do-thing") -> dict[str, object]:
    return {
        "manifest_version": "0.1",
        "id": skill_id,
        "name": "Do Thing",
        "description": "Does a thing.",
        "owner": {"agent_id": "did:web:example.com"},
        "version": "0.1.0",
        "io": {
            "inputs": [{"name": "x", "media_type": "application/json"}],
            "outputs": [{"name": "y", "media_type": "application/json"}],
        },
        "transfer_modes": {
            "delegate": {"supported": True},
            "lease": {"supported": False},
            "teach": {"supported": False},
            "compose": {"supported": False},
        },
    }
