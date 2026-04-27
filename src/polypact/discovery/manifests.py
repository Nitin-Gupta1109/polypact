"""Manifest discovery endpoints (``PROTOCOL_SPEC.md`` §4.2).

Serves ``GET /polypact/v1/manifests`` and ``GET /polypact/v1/manifests/{skill_id}``
backed by a :class:`~polypact.manifest.ManifestStore`. The list endpoint
returns the cursor-paginated envelope from the spec; pagination itself is a
no-op in v0.1 (``next_cursor`` is always ``null``).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from polypact.errors import UnknownSkillError
from polypact.manifest import ManifestStore, SkillManifest

MANIFESTS_PATH = "/polypact/v1/manifests"
"""List endpoint per ``PROTOCOL_SPEC.md`` §2.1."""


class ManifestListResponse(BaseModel):
    """Wire envelope for the manifest list endpoint."""

    model_config = ConfigDict(extra="forbid")

    manifests: list[SkillManifest]
    next_cursor: str | None = None


def build_manifest_router(store: ManifestStore) -> APIRouter:
    """Build the manifest discovery router backed by ``store``."""
    router = APIRouter()

    @router.get(MANIFESTS_PATH)
    async def list_manifests() -> ManifestListResponse:
        return ManifestListResponse(manifests=store.list(), next_cursor=None)

    @router.get(MANIFESTS_PATH + "/{skill_id:path}")
    async def get_manifest(skill_id: str) -> SkillManifest:
        try:
            return store.get(skill_id)
        except UnknownSkillError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
