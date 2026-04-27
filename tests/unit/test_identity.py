"""Tests for the identity stack: Ed25519 keys, signing, did:web resolution."""

from __future__ import annotations

import httpx
import pytest

from polypact.errors import AuthorizationFailedError
from polypact.identity import (
    AgentKeypair,
    DidDocument,
    DidResolver,
    build_did_document,
    did_web_to_url,
    public_key_from_b64,
    sign,
    verify,
)

# --- Keys ---


def test_keypair_round_trips_through_base64() -> None:
    pair = AgentKeypair.generate(did="did:web:example.com")
    encoded = pair.public_key_b64()
    restored = public_key_from_b64(encoded)
    assert restored.public_bytes_raw() == pair.public_key_bytes()


# --- Signing ---


def test_sign_then_verify_round_trip() -> None:
    pair = AgentKeypair.generate(did="did:web:provider.com")
    payload = {"agreement_id": "abc", "skill_id": "did:web:provider.com#x", "n": 42}
    jws = sign(payload, keypair=pair)
    parsed = verify(jws, public_key=pair.public_key)
    assert parsed == payload


def test_verify_rejects_tampered_payload() -> None:
    pair = AgentKeypair.generate(did="did:web:provider.com")
    jws = sign({"x": 1}, keypair=pair)
    header, _, signature = jws.split(".")
    # Replace payload with a different (un-signed) payload.
    other_jws = sign({"x": 2}, keypair=pair).split(".")[1]
    forged = f"{header}.{other_jws}.{signature}"
    with pytest.raises(AuthorizationFailedError, match="signature did not verify"):
        verify(forged, public_key=pair.public_key)


def test_verify_rejects_signature_from_wrong_key() -> None:
    pair_a = AgentKeypair.generate(did="did:web:a.com")
    pair_b = AgentKeypair.generate(did="did:web:b.com")
    jws = sign({"hello": "world"}, keypair=pair_a)
    with pytest.raises(AuthorizationFailedError, match="signature did not verify"):
        verify(jws, public_key=pair_b.public_key)


def test_verify_rejects_unsupported_alg() -> None:
    pair = AgentKeypair.generate(did="did:web:provider.com")
    # Build a JWS by hand with alg=HS256 (unsupported).
    import base64
    import json

    header = (
        base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "kid": pair.key_id}, sort_keys=True).encode(),
        )
        .rstrip(b"=")
        .decode()
    )
    payload = base64.urlsafe_b64encode(b'{"x":1}').rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(b"fake").rstrip(b"=").decode()
    with pytest.raises(AuthorizationFailedError, match="unsupported alg"):
        verify(f"{header}.{payload}.{sig}", public_key=pair.public_key)


# --- did:web ---


def test_did_web_to_url_simple_host() -> None:
    assert did_web_to_url("did:web:example.com") == "https://example.com/.well-known/did.json"


def test_did_web_to_url_with_path() -> None:
    assert did_web_to_url("did:web:example.com:foo:bar") == "https://example.com/foo/bar/did.json"


def test_did_web_to_url_rejects_other_methods() -> None:
    with pytest.raises(ValueError, match="not a did:web"):
        did_web_to_url("did:key:z6Mk...")


def test_did_document_find_key_returns_public_key() -> None:
    pair = AgentKeypair.generate(did="did:web:example.com")
    doc = DidDocument.model_validate(
        build_did_document(
            did=pair.did,
            key_id=pair.key_id,
            public_key_b64=pair.public_key_b64(),
        ),
    )
    found = doc.find_key(pair.key_id)
    assert found.public_bytes_raw() == pair.public_key_bytes()


def test_did_document_find_key_raises_for_unknown_id() -> None:
    pair = AgentKeypair.generate(did="did:web:example.com")
    doc = DidDocument.model_validate(
        build_did_document(
            did=pair.did,
            key_id=pair.key_id,
            public_key_b64=pair.public_key_b64(),
        ),
    )
    with pytest.raises(AuthorizationFailedError, match="not present"):
        doc.find_key("did:web:example.com#missing")


async def test_resolver_fetches_and_caches_did_document() -> None:
    pair = AgentKeypair.generate(did="did:web:example.com")
    document = build_did_document(
        did=pair.did,
        key_id=pair.key_id,
        public_key_b64=pair.public_key_b64(),
    )

    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert str(request.url) == "https://example.com/.well-known/did.json"
        return httpx.Response(200, json=document)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = DidResolver(http_client=client)
        first = await resolver.resolve(pair.did)
        second = await resolver.resolve(pair.did)
        assert first.id == pair.did
        assert second is first  # cached
        assert request_count == 1
