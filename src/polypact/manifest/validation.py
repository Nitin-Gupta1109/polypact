"""Beyond-schema validation rules for Skill Manifests.

Pydantic enforces shape and per-field constraints. This module enforces the
cross-field semantic rules from ``PROTOCOL_SPEC.md`` §3.2 that don't fit a
field validator.

Use :func:`validate_manifest` after parsing to surface domain-level violations
as :class:`~polypact.errors.ManifestValidationError`.
"""

from __future__ import annotations

from polypact.errors import ManifestValidationError
from polypact.manifest.schemas import SUPPORTED_MANIFEST_VERSIONS, SkillManifest


def validate_manifest(manifest: SkillManifest) -> None:
    """Validate a parsed manifest against ``PROTOCOL_SPEC.md`` §3.2 rules.

    Args:
        manifest: A parsed :class:`SkillManifest`.

    Raises:
        ManifestValidationError: If any beyond-schema rule fails.
    """
    if manifest.manifest_version not in SUPPORTED_MANIFEST_VERSIONS:
        msg = (
            f"manifest_version {manifest.manifest_version!r} is not supported; "
            f"supported versions: {SUPPORTED_MANIFEST_VERSIONS}"
        )
        raise ManifestValidationError(msg)

    modes = manifest.transfer_modes
    any_supported = (
        modes.delegate.supported
        or modes.lease.supported
        or modes.teach.supported
        or modes.compose.supported
    )
    if not any_supported:
        msg = "at least one transfer mode must be supported"
        raise ManifestValidationError(msg)

    if modes.compose.supported and not modes.compose.compose_modes:
        msg = "compose.supported=True requires at least one entry in compose_modes"
        raise ManifestValidationError(msg)
