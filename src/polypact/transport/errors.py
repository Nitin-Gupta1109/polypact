"""Mapping from Polypact domain errors to JSON-RPC 2.0 error codes.

Kept separate from :mod:`polypact.errors` so the domain layer has no transport
dependency. Subclasses of :class:`~polypact.errors.PolypactError` carry a
``code`` attribute; this module just hands it back, plus the standard JSON-RPC
codes for envelope-level failures (parse error, invalid request, etc.).
"""

from __future__ import annotations

from polypact.errors import PolypactError

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def code_for(exc: BaseException) -> int:
    """Return the JSON-RPC error code for an exception.

    Polypact errors return their declared code; anything else is treated as
    an internal error per the JSON-RPC 2.0 spec.
    """
    if isinstance(exc, PolypactError):
        return exc.code
    return INTERNAL_ERROR
