"""The ``teach`` transfer primitive (``PROTOCOL_SPEC.md`` §6.3).

Provider transfers a skill artifact (prompt template, workflow definition,
tool descriptor) to the initiator, who then runs it locally. The protocol
standardizes only the *transfer*; artifact runtime semantics are framework-
specific (LangChain, AutoGen, etc.).

Implementation: the server registers an artifact for each skill that
supports teach mode. On ``polypact.transfer.teach``, the primitive verifies
the agreement and returns the artifact + license terms.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from polypact.errors import AgreementViolatedError, UnknownSkillError
from polypact.negotiation import Agreement

ArtifactType = Literal["prompt_template", "workflow", "tool_descriptor"]


class TeachArtifact(BaseModel):
    """A teachable artifact registered for a skill."""

    model_config = ConfigDict(extra="forbid")

    artifact_type: ArtifactType
    artifact: dict[str, Any]
    license: dict[str, Any] = Field(default_factory=dict)


class TeachResult(BaseModel):
    """Wire response for ``polypact.transfer.teach`` (§6.3)."""

    model_config = ConfigDict(extra="forbid")

    artifact_type: ArtifactType
    artifact: dict[str, Any]
    license: dict[str, Any]


class TeachPrimitive:
    """Holds the registry of teachable artifacts keyed by skill ID."""

    def __init__(self) -> None:
        self._artifacts: dict[str, TeachArtifact] = {}

    def register(self, skill_id: str, artifact: TeachArtifact) -> None:
        """Register ``artifact`` as the teach payload for ``skill_id``."""
        if skill_id in self._artifacts:
            msg = f"teach artifact for {skill_id!r} is already registered"
            raise ValueError(msg)
        self._artifacts[skill_id] = artifact

    def has_artifact(self, skill_id: str) -> bool:
        """Return True if a teach artifact is registered for ``skill_id``."""
        return skill_id in self._artifacts

    def transfer(self, agreement: Agreement) -> TeachResult:
        """Return the teach artifact bound to ``agreement.skill_id``."""
        if agreement.transfer_mode != "teach":
            msg = (
                f"agreement {agreement.agreement_id} is for mode "
                f"{agreement.transfer_mode!r}, not 'teach'"
            )
            raise AgreementViolatedError(msg)
        artifact = self._artifacts.get(agreement.skill_id)
        if artifact is None:
            msg = f"no teach artifact registered for skill {agreement.skill_id!r}"
            raise UnknownSkillError(msg)
        return TeachResult(
            artifact_type=artifact.artifact_type,
            artifact=artifact.artifact,
            license=artifact.license,
        )
