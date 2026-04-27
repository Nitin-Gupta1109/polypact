"""Shared test fixtures.

A canonical valid manifest fixture is provided here because it's reused across
schema, validation, registry, and discovery tests. Per-module fixtures should
live alongside their tests.
"""

from __future__ import annotations

import pytest

from polypact.manifest import (
    SLA,
    ComposeMode,
    DataHandling,
    DelegateMode,
    IOField,
    IOSpec,
    LeaseMode,
    Owner,
    Pricing,
    SkillManifest,
    TeachMode,
    Terms,
    TransferModes,
)


@pytest.fixture
def sample_manifest() -> SkillManifest:
    """A fully-populated valid manifest mirroring the example in PROTOCOL_SPEC.md §3.1."""
    return SkillManifest(
        manifest_version="0.1",
        id="did:web:companyB.com#extract-invoice",
        name="Invoice Field Extraction",
        description="Extract structured fields from invoice PDFs.",
        owner=Owner(
            agent_id="did:web:companyB.com",
            display_name="CompanyB Document Agent",
        ),
        version="1.2.0",
        io=IOSpec(
            inputs=[
                IOField(
                    name="document",
                    media_type="application/pdf",
                    schema_ref="https://schemas.example.com/pdf-input.json",
                    required=True,
                ),
            ],
            outputs=[
                IOField(
                    name="fields",
                    media_type="application/json",
                    schema_ref="https://schema.org/Invoice",
                ),
            ],
        ),
        preconditions=["input.document.size <= 10485760"],
        postconditions=["output.fields.confidence >= 0.7"],
        transfer_modes=TransferModes(
            delegate=DelegateMode(supported=True),
            lease=LeaseMode(supported=True, max_invocations=1000, max_ttl_seconds=86400),
            teach=TeachMode(supported=False, reason="proprietary"),
            compose=ComposeMode(supported=True, compose_modes=["sequential", "parallel"]),
        ),
        terms=Terms(
            pricing=Pricing(model="per_invocation", amount=0.05, currency="USD"),
            data_handling=DataHandling(
                retention_seconds=0,
                processing_locations=["EU"],
                subprocessors_allowed=False,
            ),
            sla=SLA(p50_latency_ms=2000, p99_latency_ms=8000, availability=0.99),
        ),
        metadata={},
    )
