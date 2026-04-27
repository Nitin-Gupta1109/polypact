"""Agent identity: Ed25519 keys, ``did:web`` resolution, JWS signing."""

from polypact.identity.did_web import (
    ED25519_KEY_TYPE,
    DidDocument,
    DidResolver,
    VerificationMethod,
    build_did_document,
    did_web_to_url,
)
from polypact.identity.keys import AgentKeypair, public_key_from_b64
from polypact.identity.signing import canonicalize, sign, split_jws, verify

__all__ = [
    "ED25519_KEY_TYPE",
    "AgentKeypair",
    "DidDocument",
    "DidResolver",
    "VerificationMethod",
    "build_did_document",
    "canonicalize",
    "did_web_to_url",
    "public_key_from_b64",
    "sign",
    "split_jws",
    "verify",
]
