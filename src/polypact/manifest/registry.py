"""In-memory store for an agent's own skill manifests.

The registry is deliberately a thin wrapper. Persistence backends (Postgres,
Redis) are deferred to ``FUTURE_WORK.md`` §5; the public surface here is the
contract those backends must satisfy.
"""

from __future__ import annotations

from typing import Protocol

from polypact.errors import UnknownSkillError
from polypact.manifest.schemas import SkillManifest
from polypact.manifest.validation import validate_manifest


class ManifestStore(Protocol):
    """Read interface for any manifest storage backend."""

    def list(self) -> list[SkillManifest]:
        """Return all manifests known to the store."""
        ...

    def get(self, skill_id: str) -> SkillManifest:
        """Return a single manifest by skill ID.

        Raises:
            UnknownSkillError: If no manifest matches ``skill_id``.
        """
        ...


class ManifestRegistry:
    """In-memory :class:`ManifestStore` keyed by skill ID.

    Manifests are validated on registration; an invalid manifest never enters
    the registry. The store preserves insertion order on listing.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, SkillManifest] = {}

    def register(self, manifest: SkillManifest) -> None:
        """Validate and store a manifest.

        Raises:
            ManifestValidationError: If beyond-schema validation fails.
            ValueError: If a manifest with the same ID is already registered.
        """
        validate_manifest(manifest)
        if manifest.id in self._by_id:
            msg = f"manifest with id {manifest.id!r} is already registered"
            raise ValueError(msg)
        self._by_id[manifest.id] = manifest

    def list(self) -> list[SkillManifest]:
        """Return all manifests in registration order."""
        return list(self._by_id.values())

    def get(self, skill_id: str) -> SkillManifest:
        """Return a single manifest, raising :class:`UnknownSkillError` if absent."""
        try:
            return self._by_id[skill_id]
        except KeyError as exc:
            raise UnknownSkillError(f"unknown skill: {skill_id!r}") from exc

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, skill_id: object) -> bool:
        return isinstance(skill_id, str) and skill_id in self._by_id
