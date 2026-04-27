"""Tests for the in-memory ManifestRegistry."""

from __future__ import annotations

import pytest

from polypact.errors import UnknownSkillError
from polypact.manifest import ManifestRegistry, SkillManifest


def test_register_and_get(sample_manifest: SkillManifest) -> None:
    registry = ManifestRegistry()
    registry.register(sample_manifest)
    assert registry.get(sample_manifest.id) == sample_manifest
    assert sample_manifest.id in registry
    assert len(registry) == 1


def test_list_preserves_insertion_order(sample_manifest: SkillManifest) -> None:
    second = sample_manifest.model_copy(
        update={"id": "did:web:companyB.com#another-skill"},
    )
    registry = ManifestRegistry()
    registry.register(sample_manifest)
    registry.register(second)
    assert [m.id for m in registry.list()] == [sample_manifest.id, second.id]


def test_get_unknown_raises(sample_manifest: SkillManifest) -> None:
    registry = ManifestRegistry()
    registry.register(sample_manifest)
    with pytest.raises(UnknownSkillError):
        registry.get("did:web:nope.com#missing")


def test_duplicate_registration_rejected(sample_manifest: SkillManifest) -> None:
    registry = ManifestRegistry()
    registry.register(sample_manifest)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(sample_manifest)


def test_invalid_manifest_never_enters_registry(sample_manifest: SkillManifest) -> None:
    from polypact.errors import ManifestValidationError
    from polypact.manifest import (
        ComposeMode,
        DelegateMode,
        LeaseMode,
        TeachMode,
        TransferModes,
    )

    bad = sample_manifest.model_copy(
        update={
            "transfer_modes": TransferModes(
                delegate=DelegateMode(supported=False),
                lease=LeaseMode(supported=False),
                teach=TeachMode(supported=False),
                compose=ComposeMode(supported=False, compose_modes=[]),
            ),
        },
    )
    registry = ManifestRegistry()
    with pytest.raises(ManifestValidationError):
        registry.register(bad)
    assert len(registry) == 0
