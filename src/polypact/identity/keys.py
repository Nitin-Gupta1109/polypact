"""Ed25519 keypair management for Polypact agent identities.

Wraps :mod:`cryptography.hazmat.primitives.asymmetric.ed25519` with
serialization helpers and a small in-memory keystore. File-based key custody
is sufficient for v0.1; HSM/KMS integration is deferred per
``FUTURE_WORK.md`` §4.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric import ed25519


@dataclass(frozen=True)
class AgentKeypair:
    """An Ed25519 keypair bound to a DID-based key identifier.

    Attributes:
        did: The owning agent's DID (e.g., ``did:web:example.com``).
        key_id: The full DID URL of this key (e.g., ``did:web:example.com#key-1``).
        private_key: Ed25519 private key (sign side).
        public_key: Ed25519 public key (verify side).
    """

    did: str
    key_id: str
    private_key: ed25519.Ed25519PrivateKey
    public_key: ed25519.Ed25519PublicKey

    @classmethod
    def generate(cls, *, did: str, key_id: str | None = None) -> AgentKeypair:
        """Generate a fresh Ed25519 keypair for ``did``.

        ``key_id`` defaults to ``"{did}#key-1"``; pass an explicit value if
        the agent rotates or maintains multiple keys.
        """
        private = ed25519.Ed25519PrivateKey.generate()
        return cls(
            did=did,
            key_id=key_id or f"{did}#key-1",
            private_key=private,
            public_key=private.public_key(),
        )

    def public_key_bytes(self) -> bytes:
        """Return the raw 32-byte public key."""
        from cryptography.hazmat.primitives import serialization

        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def public_key_b64(self) -> str:
        """Return the public key as base64url (no padding)."""
        return base64.urlsafe_b64encode(self.public_key_bytes()).rstrip(b"=").decode()


def public_key_from_b64(value: str) -> ed25519.Ed25519PublicKey:
    """Decode a base64url-encoded raw Ed25519 public key."""
    padded = value + "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode(padded)
    return ed25519.Ed25519PublicKey.from_public_bytes(raw)
