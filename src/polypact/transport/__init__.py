"""Wire-level transport: JSON-RPC 2.0 over HTTP."""

from polypact.transport.http_client import HttpTransport
from polypact.transport.http_server import RPC_PATH, build_rpc_router
from polypact.transport.jsonrpc import (
    Dispatcher,
    Handler,
    JsonRpcError,
    JsonRpcId,
    JsonRpcRequest,
    JsonRpcResponse,
    parse_error_response,
)

__all__ = [
    "RPC_PATH",
    "Dispatcher",
    "Handler",
    "HttpTransport",
    "JsonRpcError",
    "JsonRpcId",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "build_rpc_router",
    "parse_error_response",
]
