"""Compact JWS-style signing over canonical JSON.

The wire format is ``header_b64.payload_b64.signature_b64`` where:

* ``header`` = ``{"alg": "EdDSA", "kid": "<did_url>"}``
* ``payload`` = ``json.dumps(obj, sort_keys=True, separators=(",", ":"))``
  (canonical JSON; keys sorted, no whitespace)
* ``signature`` = ``Ed25519(header_b64 + "." + payload_b64)``

This is structurally compact JWS (RFC 7515) restricted to ``EdDSA``. The
canonicalization is the simplest correct option for the reference impl;
production deployments should adopt RFC 8785 (JCS) — documented in
``DESIGN_NOTES.md``.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from polypact.errors import AuthorizationFailedError
from polypact.identity.keys import AgentKeypair


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded)


def canonicalize(obj: Any) -> bytes:  # noqa: ANN401  (free-form JSON in)
    """Canonicalize ``obj`` to bytes for signing.

    Sorted keys, compact separators, UTF-8. Sufficient deterministic JSON
    for v0.1; not full RFC 8785.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sign(payload: Any, *, keypair: AgentKeypair) -> str:  # noqa: ANN401
    """Sign ``payload`` and return a compact JWS string."""
    header_b64 = _b64url_encode(canonicalize({"alg": "EdDSA", "kid": keypair.key_id}))
    payload_b64 = _b64url_encode(canonicalize(payload))
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = keypair.private_key.sign(signing_input)
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def split_jws(jws: str) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    """Split a compact JWS into (header, payload, signature_bytes)."""
    parts = jws.split(".")
    if len(parts) != 3:
        msg = "compact JWS must have exactly three parts"
        raise AuthorizationFailedError(msg)
    header_b64, payload_b64, signature_b64 = parts
    header = json.loads(_b64url_decode(header_b64))
    payload = json.loads(_b64url_decode(payload_b64))
    signature = _b64url_decode(signature_b64)
    if not isinstance(header, dict) or not isinstance(payload, dict):
        msg = "JWS header and payload must both be JSON objects"
        raise AuthorizationFailedError(msg)
    return header, payload, signature


def verify(jws: str, *, public_key: ed25519.Ed25519PublicKey) -> dict[str, Any]:
    """Verify a compact JWS against ``public_key``; return the parsed payload.

    Raises :class:`AuthorizationFailedError` on any failure (bad shape,
    unsupported algorithm, signature mismatch).
    """
    parts = jws.split(".")
    if len(parts) != 3:
        msg = "compact JWS must have exactly three parts"
        raise AuthorizationFailedError(msg)
    header_b64, payload_b64, signature_b64 = parts
    header = json.loads(_b64url_decode(header_b64))
    if header.get("alg") != "EdDSA":
        msg = f"unsupported alg: {header.get('alg')!r}"
        raise AuthorizationFailedError(msg)
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = _b64url_decode(signature_b64)
    try:
        public_key.verify(signature, signing_input)
    except InvalidSignature as exc:
        msg = "JWS signature did not verify"
        raise AuthorizationFailedError(msg) from exc
    payload = json.loads(_b64url_decode(payload_b64))
    if not isinstance(payload, dict):
        msg = "JWS payload must be a JSON object"
        raise AuthorizationFailedError(msg)
    return payload
