"""Tests for beyond-schema manifest validation (PROTOCOL_SPEC.md §3.2)."""

from __future__ import annotations

import pytest

from polypact.errors import ManifestValidationError
from polypact.manifest import (
    ComposeMode,
    DelegateMode,
    LeaseMode,
    SkillManifest,
    TeachMode,
    TransferModes,
    validate_manifest,
)


def test_sample_manifest_passes(sample_manifest: SkillManifest) -> None:
    validate_manifest(sample_manifest)


def test_at_least_one_transfer_mode_must_be_supported(sample_manifest: SkillManifest) -> None:
    none_supported = sample_manifest.model_copy(
        update={
            "transfer_modes": TransferModes(
                delegate=DelegateMode(supported=False),
                lease=LeaseMode(supported=False),
                teach=TeachMode(supported=False),
                compose=ComposeMode(supported=False, compose_modes=[]),
            ),
        },
    )
    with pytest.raises(ManifestValidationError, match="at least one transfer mode"):
        validate_manifest(none_supported)


def test_compose_supported_requires_compose_modes(sample_manifest: SkillManifest) -> None:
    bad = sample_manifest.model_copy(
        update={
            "transfer_modes": TransferModes(
                delegate=DelegateMode(supported=True),
                lease=LeaseMode(supported=False),
                teach=TeachMode(supported=False),
                compose=ComposeMode(supported=True, compose_modes=[]),
            ),
        },
    )
    with pytest.raises(ManifestValidationError, match="compose_modes"):
        validate_manifest(bad)
