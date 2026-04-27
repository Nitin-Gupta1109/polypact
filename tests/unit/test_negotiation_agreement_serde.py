"""Round-trip serialize → deserialize an Agreement, per ROADMAP Phase 3."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from polypact.manifest import Pricing
from polypact.negotiation import (
    Agreement,
    LeaseTerms,
    Parties,
    ProposedTerms,
)


def test_agreement_round_trips_through_json() -> None:
    now = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
    original = Agreement(
        agreement_id=uuid4(),
        negotiation_id=uuid4(),
        skill_id="did:web:provider.com#extract-invoice",
        transfer_mode="lease",
        terms=ProposedTerms(
            pricing=Pricing(model="per_invocation", amount=0.04, currency="USD"),
            lease=LeaseTerms(max_invocations=50, ttl_seconds=3600),
        ),
        parties=Parties(
            initiator="did:web:initiator.com",
            provider="did:web:provider.com",
        ),
        valid_from=now,
        valid_until=now + timedelta(hours=1),
        signatures={},
    )
    payload = original.model_dump_json()
    restored = Agreement.model_validate_json(payload)
    assert restored == original
    assert restored.signatures == {}
