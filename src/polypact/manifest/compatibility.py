"""Composition compatibility checks (``PROTOCOL_SPEC.md`` §3.3).

Two compose modes are defined:

* **sequential** — A's outputs feed B's inputs. Per §3.3, two skills are
  sequentially composable iff for some output ``o`` of A and some input ``i``
  of B, ``o.media_type == i.media_type`` AND (``o.schema_ref == i.schema_ref``
  OR a registered schema-compatibility relation exists).
* **parallel** — both skills are called with the same input. The spec is
  silent on the semantics; this implementation defines parallel compatibility
  as "for every required input of B there is a matching required input of A
  by ``name`` with compatible ``media_type`` / ``schema_ref``" (and vice-versa
  for any required input of A). Documented in DESIGN_NOTES.

The :class:`SchemaRelations` registry lets operators declare compatibility
between distinct ``schema_ref`` URIs (e.g., a custom Invoice schema is
acceptable wherever ``schema.org/Invoice`` is expected).
"""

from __future__ import annotations

from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field

from polypact.manifest.schemas import ComposeKind, IOField, SkillManifest


class SchemaRelations:
    """Registry of declared schema-compatibility relations.

    Relations are directional by default: registering ``a -> b`` means a payload
    described by ``a`` can be consumed where ``b`` is expected. Use
    :meth:`register_bidirectional` for symmetric relations.
    """

    def __init__(self) -> None:
        self._edges: set[tuple[str, str]] = set()

    def register(self, source: str, target: str) -> None:
        """Declare that ``source`` is acceptable wherever ``target`` is expected."""
        self._edges.add((source, target))

    def register_bidirectional(self, a: str, b: str) -> None:
        """Declare a symmetric compatibility between ``a`` and ``b``."""
        self._edges.add((a, b))
        self._edges.add((b, a))

    def is_compatible(self, source: str | None, target: str | None) -> bool:
        """Return True if a payload of ``source`` schema fits ``target`` slot."""
        if source is None or target is None:
            # Untyped on either side: per §3.3 the schema_ref check is OR'd
            # with media_type, so absent schema_ref means we fall back to
            # media_type only (handled at call sites). Here we say "no
            # schema-level compatibility relation."
            return False
        if source == target:
            return True
        return (source, target) in self._edges


class FieldMatch(BaseModel):
    """A single matched output→input pair within a compatibility report."""

    model_config = ConfigDict(extra="forbid")

    output_field: str
    input_field: str
    media_type: str
    schema_ref_match: bool
    via_relation: bool = False


class CompatibilityReport(BaseModel):
    """Result of a composition check between two skill manifests."""

    model_config = ConfigDict(extra="forbid")

    compatible: bool
    mode: ComposeKind
    matches: list[FieldMatch] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


def _fields_compatible(
    out_field: IOField,
    in_field: IOField,
    relations: SchemaRelations,
) -> tuple[bool, bool]:
    """Return (compatible, via_relation) for two fields per §3.3.

    The first element is true if the fields are compatible at all; the second
    indicates whether a registered schema-compatibility relation was needed
    (informational only).
    """
    if out_field.media_type != in_field.media_type:
        return False, False
    if out_field.schema_ref is None or in_field.schema_ref is None:
        return True, False
    if out_field.schema_ref == in_field.schema_ref:
        return True, False
    if relations.is_compatible(out_field.schema_ref, in_field.schema_ref):
        return True, True
    return False, False


def check_sequential(
    a: SkillManifest,
    b: SkillManifest,
    relations: SchemaRelations | None = None,
) -> CompatibilityReport:
    """Check whether ``a`` then ``b`` is a valid sequential composition.

    Per §3.3 the relation is "exists o of A, exists i of B such that ...".
    The returned report lists every matching pair so callers can pick a
    specific wiring; ``compatible=True`` iff at least one pair matched.
    """
    rels = relations or SchemaRelations()
    matches: list[FieldMatch] = []
    for out_field in a.io.outputs:
        for in_field in b.io.inputs:
            ok, via_rel = _fields_compatible(out_field, in_field, rels)
            if ok:
                matches.append(
                    FieldMatch(
                        output_field=out_field.name,
                        input_field=in_field.name,
                        media_type=out_field.media_type,
                        schema_ref_match=out_field.schema_ref == in_field.schema_ref,
                        via_relation=via_rel,
                    ),
                )
    if matches:
        return CompatibilityReport(compatible=True, mode="sequential", matches=matches)
    reasons = [
        f"no output of {a.id!r} matches any input of {b.id!r} on media_type+schema_ref",
    ]
    return CompatibilityReport(compatible=False, mode="sequential", reasons=reasons)


def check_parallel(
    a: SkillManifest,
    b: SkillManifest,
    relations: SchemaRelations | None = None,
) -> CompatibilityReport:
    """Check whether ``a`` and ``b`` accept the same input shape.

    Parallel semantics aren't fully specified in the spec; this implementation
    treats two skills as parallel-compatible when each required input of one
    has a same-name, same-shape counterpart on the other.
    """
    rels = relations or SchemaRelations()
    reasons: list[str] = []

    a_inputs = {field.name: field for field in a.io.inputs}
    b_inputs = {field.name: field for field in b.io.inputs}

    for name, a_field in a_inputs.items():
        if not a_field.required:
            continue
        b_field = b_inputs.get(name)
        if b_field is None:
            reasons.append(f"required input {name!r} of {a.id!r} missing on {b.id!r}")
            continue
        ok, _ = _fields_compatible(a_field, b_field, rels)
        if not ok:
            reasons.append(
                f"input {name!r} mismatched between {a.id!r} and {b.id!r} "
                f"on media_type or schema_ref",
            )

    for name, b_field in b_inputs.items():
        if not b_field.required:
            continue
        if name not in a_inputs:
            reasons.append(f"required input {name!r} of {b.id!r} missing on {a.id!r}")

    if reasons:
        return CompatibilityReport(compatible=False, mode="parallel", reasons=reasons)
    return CompatibilityReport(compatible=True, mode="parallel")


def check_composition(
    manifests: list[SkillManifest],
    mode: ComposeKind,
    relations: SchemaRelations | None = None,
) -> CompatibilityReport:
    """Pairwise-walk an n-ary composition.

    For ``sequential`` mode, every adjacent pair must be sequentially
    composable. For ``parallel`` mode, all skills must be pairwise parallel-
    compatible. Returns a single report; on failure, ``reasons`` aggregates
    the failing pair(s).
    """
    if len(manifests) < 2:
        msg = "check_composition requires at least two manifests"
        raise ValueError(msg)
    if mode == "sequential":
        all_matches: list[FieldMatch] = []
        for left, right in pairwise(manifests):
            report = check_sequential(left, right, relations)
            if not report.compatible:
                return CompatibilityReport(
                    compatible=False,
                    mode="sequential",
                    reasons=report.reasons,
                )
            all_matches.extend(report.matches)
        return CompatibilityReport(
            compatible=True,
            mode="sequential",
            matches=all_matches,
        )
    # parallel
    reasons: list[str] = []
    for i, left in enumerate(manifests):
        for right in manifests[i + 1 :]:
            report = check_parallel(left, right, relations)
            if not report.compatible:
                reasons.extend(report.reasons)
    if reasons:
        return CompatibilityReport(compatible=False, mode="parallel", reasons=reasons)
    return CompatibilityReport(compatible=True, mode="parallel")
