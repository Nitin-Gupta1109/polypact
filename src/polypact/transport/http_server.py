"""HTTP transport: FastAPI router that mounts the JSON-RPC entry point.

The router is intentionally narrow — it holds *no* protocol semantics. It
hands JSON bodies to a :class:`Dispatcher` and translates the dispatcher's
return value into HTTP status codes per JSON-RPC 2.0 conventions:

* dispatcher returns ``dict`` → 200 OK with that body
* dispatcher returns ``list`` → 200 OK with the batch body
* dispatcher returns ``None`` (notification) → 204 No Content

A malformed JSON body becomes a JSON-RPC parse error (-32700) at 200 OK;
HTTP 4xx is reserved for transport-level failures (wrong method, etc.).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response

from polypact.transport.jsonrpc import Dispatcher, parse_error_response

RPC_PATH = "/polypact/v1/rpc"
"""Mounted RPC route per ``PROTOCOL_SPEC.md`` §2.1."""


def build_rpc_router(dispatcher: Dispatcher) -> APIRouter:
    """Build a FastAPI router that serves ``dispatcher`` at :data:`RPC_PATH`."""
    router = APIRouter()

    @router.post(RPC_PATH)
    async def rpc_endpoint(request: Request) -> Response:
        raw = await request.body()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            error_body = parse_error_response(None, f"invalid JSON: {exc.msg}")
            return Response(
                content=json.dumps(error_body),
                media_type="application/json",
                status_code=200,
            )

        result = await dispatcher.dispatch(payload)
        if result is None:
            return Response(status_code=204)
        return Response(
            content=json.dumps(result),
            media_type="application/json",
            status_code=200,
        )

    return router
