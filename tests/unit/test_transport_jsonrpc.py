"""Tests for JSON-RPC 2.0 framing and dispatch."""

from __future__ import annotations

from typing import Any

import pytest

from polypact.errors import UnknownSkillError
from polypact.transport.jsonrpc import Dispatcher


@pytest.fixture
def dispatcher() -> Dispatcher:
    d = Dispatcher()

    async def echo(params: dict[str, Any]) -> dict[str, Any]:
        return {"echoed": params}

    async def boom(_: dict[str, Any]) -> dict[str, Any]:
        raise UnknownSkillError("nope", data={"hint": "register first"})

    async def crash(_: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("kaboom")

    d.register("echo", echo)
    d.register("boom", boom)
    d.register("crash", crash)
    return d


async def test_successful_call_returns_result(dispatcher: Dispatcher) -> None:
    response = await dispatcher.dispatch(
        {"jsonrpc": "2.0", "method": "echo", "params": {"x": 1}, "id": "abc"},
    )
    assert response == {"jsonrpc": "2.0", "id": "abc", "result": {"echoed": {"x": 1}}}


async def test_method_not_found(dispatcher: Dispatcher) -> None:
    response = await dispatcher.dispatch(
        {"jsonrpc": "2.0", "method": "missing", "params": {}, "id": 1},
    )
    assert isinstance(response, dict)
    assert response["error"]["code"] == -32601


async def test_polypact_error_propagates_with_code(dispatcher: Dispatcher) -> None:
    response = await dispatcher.dispatch(
        {"jsonrpc": "2.0", "method": "boom", "params": {}, "id": 7},
    )
    assert isinstance(response, dict)
    assert response["error"]["code"] == UnknownSkillError.code
    assert response["error"]["data"] == {"hint": "register first"}


async def test_unexpected_exception_becomes_internal_error(dispatcher: Dispatcher) -> None:
    response = await dispatcher.dispatch(
        {"jsonrpc": "2.0", "method": "crash", "params": {}, "id": 9},
    )
    assert isinstance(response, dict)
    assert response["error"]["code"] == -32603


async def test_invalid_request_envelope(dispatcher: Dispatcher) -> None:
    response = await dispatcher.dispatch({"jsonrpc": "1.0", "method": "echo", "id": 1})
    assert isinstance(response, dict)
    assert response["error"]["code"] == -32600


async def test_invalid_params_must_be_object(dispatcher: Dispatcher) -> None:
    response = await dispatcher.dispatch(
        {"jsonrpc": "2.0", "method": "echo", "params": [1, 2, 3], "id": 1},
    )
    assert isinstance(response, dict)
    assert response["error"]["code"] == -32602


async def test_notification_produces_no_response(dispatcher: Dispatcher) -> None:
    response = await dispatcher.dispatch(
        {"jsonrpc": "2.0", "method": "echo", "params": {}},
    )
    assert response is None


async def test_notification_for_unknown_method_still_no_response(
    dispatcher: Dispatcher,
) -> None:
    response = await dispatcher.dispatch(
        {"jsonrpc": "2.0", "method": "missing", "params": {}},
    )
    assert response is None


async def test_batch_dispatch(dispatcher: Dispatcher) -> None:
    batch = [
        {"jsonrpc": "2.0", "method": "echo", "params": {"a": 1}, "id": 1},
        {"jsonrpc": "2.0", "method": "echo", "params": {"a": 2}, "id": 2},
    ]
    responses = await dispatcher.dispatch(batch)
    assert isinstance(responses, list)
    assert len(responses) == 2
    assert {r["id"] for r in responses} == {1, 2}


async def test_double_register_rejected() -> None:
    d = Dispatcher()

    async def h(_: dict[str, Any]) -> None:
        return None

    d.register("x", h)
    with pytest.raises(ValueError, match="already registered"):
        d.register("x", h)
