"""JSON-RPC 2.0 framing and dispatch.

This module is wire-level only. It does not import from :mod:`polypact.manifest`,
:mod:`polypact.negotiation`, or any other protocol module. Protocol code
registers handlers with a :class:`Dispatcher`; the dispatcher handles request
parsing, error mapping, and response shaping.

Spec reference: https://www.jsonrpc.org/specification
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from polypact.errors import PolypactError
from polypact.transport.errors import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    code_for,
)

logger = logging.getLogger(__name__)


JsonRpcId = str | int | None
"""JSON-RPC request IDs may be string, int, or null (notifications)."""


class JsonRpcRequest(BaseModel):
    """A single JSON-RPC 2.0 request envelope."""

    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"]
    method: str
    params: dict[str, Any] | list[Any] | None = None
    id: JsonRpcId = None


class JsonRpcError(BaseModel):
    """A JSON-RPC 2.0 error object."""

    model_config = ConfigDict(extra="forbid")

    code: int
    message: str
    data: Any = None


class JsonRpcResponse(BaseModel):
    """A single JSON-RPC 2.0 response envelope.

    Exactly one of ``result`` or ``error`` is populated; the other is omitted
    on the wire via :meth:`model_dump` with ``exclude_none=True``.
    """

    model_config = ConfigDict(extra="forbid")

    jsonrpc: Literal["2.0"] = "2.0"
    id: JsonRpcId = None
    result: Any = None
    error: JsonRpcError | None = None

    def to_wire(self) -> dict[str, Any]:
        """Serialize, dropping the unused branch (``result`` or ``error``)."""
        payload = self.model_dump(exclude_none=True)
        if self.error is None:
            payload.pop("error", None)
        else:
            payload.pop("result", None)
        return payload


Handler = Callable[[dict[str, Any]], Awaitable[Any]]
"""An RPC handler accepts the ``params`` dict and returns a JSON-serializable result."""


class Dispatcher:
    """In-process JSON-RPC method dispatcher.

    Handlers are registered by method name. ``dispatch`` accepts a *parsed*
    JSON object (or list, for batch requests) and returns the corresponding
    response payload(s). Transport adapters (HTTP, etc.) wrap this with
    parse-error handling and content-type negotiation.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, method: str, handler: Handler) -> None:
        """Register ``handler`` to serve calls to ``method``.

        Re-registering an existing method is a programming error.
        """
        if method in self._handlers:
            msg = f"handler for {method!r} is already registered"
            raise ValueError(msg)
        self._handlers[method] = handler

    def has(self, method: str) -> bool:
        """Return True if a handler is registered for ``method``."""
        return method in self._handlers

    async def dispatch(
        self, payload: dict[str, Any] | list[dict[str, Any]]
    ) -> dict[str, Any] | list[dict[str, Any]] | None:
        """Dispatch a single request or a batch.

        Notifications (requests without ``id``) are processed but produce no
        response per the JSON-RPC 2.0 spec. The single-dispatch case returns
        ``None`` for notifications so the transport layer can map it to e.g.
        ``204 No Content``. Batches drop notifications from the response list.
        """
        if isinstance(payload, list):
            if not payload:
                return _error_response(None, INVALID_REQUEST, "batch must be non-empty").to_wire()
            responses: list[dict[str, Any]] = []
            for item in payload:
                response = await self._dispatch_one(item)
                if response is not None:
                    responses.append(response)
            return responses
        return await self._dispatch_one(payload)

    async def _dispatch_one(self, raw: object) -> dict[str, Any] | None:
        try:
            request = JsonRpcRequest.model_validate(raw)
        except Exception as exc:
            req_id = raw.get("id") if isinstance(raw, dict) else None
            return _error_response(req_id, INVALID_REQUEST, str(exc)).to_wire()

        is_notification = request.id is None
        handler = self._handlers.get(request.method)
        if handler is None:
            if is_notification:
                return None
            return _error_response(
                request.id, METHOD_NOT_FOUND, f"method not found: {request.method!r}"
            ).to_wire()

        if not isinstance(request.params, dict):
            if is_notification:
                return None
            return _error_response(
                request.id, INVALID_PARAMS, "params must be a JSON object"
            ).to_wire()

        try:
            result = await handler(request.params)
        except PolypactError as exc:
            logger.info(
                "rpc.handler.domain_error",
                extra={"method": request.method, "code": exc.code},
            )
            if is_notification:
                return None
            return _error_response(request.id, code_for(exc), exc.message, data=exc.data).to_wire()
        except Exception as exc:
            logger.exception("rpc.handler.unexpected_error", extra={"method": request.method})
            if is_notification:
                return None
            return _error_response(request.id, code_for(exc), "internal error").to_wire()

        if is_notification:
            return None
        return _ok_response(request.id, result).to_wire()


def _ok_response(request_id: JsonRpcId, result: Any) -> JsonRpcResponse:
    return JsonRpcResponse(id=request_id, result=result)


def _error_response(
    request_id: JsonRpcId,
    code: int,
    message: str,
    *,
    data: Any = None,
) -> JsonRpcResponse:
    return JsonRpcResponse(id=request_id, error=JsonRpcError(code=code, message=message, data=data))


def parse_error_response(request_id: JsonRpcId, message: str) -> dict[str, Any]:
    """Build a wire-form parse-error response. Used by HTTP transport on bad JSON."""
    return _error_response(request_id, PARSE_ERROR, message).to_wire()


__all__ = [
    "Dispatcher",
    "Handler",
    "JsonRpcError",
    "JsonRpcId",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "parse_error_response",
]
