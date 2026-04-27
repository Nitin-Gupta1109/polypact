"""``did:web`` resolution.

Implements the W3C ``did:web`` method (https://w3c-ccg.github.io/did-method-web/)
with a minimal subset of the DID Core data model: just enough to extract an
Ed25519 verification method by ``id``.

DID document encoding: this implementation uses ``publicKeyBase64`` (raw 32
bytes, base64url, no padding) for verification methods rather than the W3C
``publicKeyMultibase``. The deviation is documented in ``DESIGN_NOTES.md``;
production implementations should adopt multibase.
"""

from __future__ import annotations

from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import BaseModel, ConfigDict, Field

from polypact.errors import AuthorizationFailedError
from polypact.identity.keys import public_key_from_b64

ED25519_KEY_TYPE = "Ed25519VerificationKey2020"


class VerificationMethod(BaseModel):
    """A single verification method on a DID document."""

    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    controller: str | None = None
    public_key_base64: str | None = Field(default=None, alias="publicKeyBase64")


class DidDocument(BaseModel):
    """Minimal DID Document model (W3C did-core subset)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    verification_method: list[VerificationMethod] = Field(
        default_factory=list,
        alias="verificationMethod",
    )

    def find_key(self, key_id: str) -> ed25519.Ed25519PublicKey:
        """Return the Ed25519 public key for ``key_id``.

        Raises:
            AuthorizationFailedError: If no matching key exists or the key
                type is unsupported.
        """
        for method in self.verification_method:
            if method.id != key_id:
                continue
            if method.type != ED25519_KEY_TYPE:
                msg = f"unsupported key type for {key_id!r}: {method.type}"
                raise AuthorizationFailedError(msg)
            if method.public_key_base64 is None:
                msg = f"verification method {key_id!r} has no publicKeyBase64"
                raise AuthorizationFailedError(msg)
            return public_key_from_b64(method.public_key_base64)
        msg = f"verification method {key_id!r} not present in DID document"
        raise AuthorizationFailedError(msg)


def did_web_to_url(did: str) -> str:
    """Map a ``did:web:...`` identifier to its DID document URL.

    ``did:web:example.com`` → ``https://example.com/.well-known/did.json``
    ``did:web:example.com:foo:bar`` → ``https://example.com/foo/bar/did.json``
    """
    if not did.startswith("did:web:"):
        msg = f"not a did:web identifier: {did!r}"
        raise ValueError(msg)
    suffix = did.removeprefix("did:web:")
    parts = suffix.split(":")
    host = parts[0]
    path = parts[1:]
    if not path:
        return f"https://{host}/.well-known/did.json"
    return f"https://{host}/{'/'.join(path)}/did.json"


class DidResolver:
    """Resolves DID documents over HTTPS with a small in-process cache.

    Tests can inject an :class:`httpx.AsyncClient` configured with
    ``httpx.MockTransport`` so resolution stays in-process.
    """

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient()
        self._cache: dict[str, DidDocument] = {}

    async def resolve(self, did: str) -> DidDocument:
        """Fetch and parse the DID document for ``did``."""
        if did in self._cache:
            return self._cache[did]
        url = did_web_to_url(did)
        response = await self._client.get(url)
        response.raise_for_status()
        document = DidDocument.model_validate(response.json())
        self._cache[did] = document
        return document

    def prime(self, did: str, document: DidDocument) -> None:
        """Insert a pre-resolved document into the cache (test convenience)."""
        self._cache[did] = document

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this resolver owns it."""
        if self._owns_client:
            await self._client.aclose()


def build_did_document(*, did: str, key_id: str, public_key_b64: str) -> dict[str, Any]:
    """Build the JSON shape an agent should publish at ``/.well-known/did.json``.

    Returned as a plain dict so callers can serve it via FastAPI without
    pulling in the model class.
    """
    return {
        "@context": "https://www.w3.org/ns/did/v1",
        "id": did,
        "verificationMethod": [
            {
                "id": key_id,
                "type": ED25519_KEY_TYPE,
                "controller": did,
                "publicKeyBase64": public_key_b64,
            },
        ],
        "authentication": [key_id],
        "assertionMethod": [key_id],
    }
