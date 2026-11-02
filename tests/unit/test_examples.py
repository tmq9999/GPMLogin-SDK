from __future__ import annotations

import ast
import asyncio
import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

from gpmlogin_sdk import AsyncGPMClient, GPMClient
from tests.conftest import json_response
from tests.fakes import AsyncFakeContext, FakeContext, FakePage, make_world

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
NAMES = ["sync_basic", "async_basic", "sync_playwright", "async_playwright"]
SECRET_WS = "ws://127.0.0.1:9222/devtools/browser/SECRET-WS-TOKEN"


def load(name: str) -> ModuleType:
    path = EXAMPLES / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"example_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", NAMES)
def test_importing_an_example_runs_nothing(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("an example touched the network on import")

    monkeypatch.setattr(httpx.Client, "send", no_network)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    module = load(name)
    assert callable(module.main)


@pytest.mark.parametrize("name", NAMES)
def test_examples_execute_only_under_the_main_guard(name: str) -> None:
    tree = ast.parse((EXAMPLES / f"{name}.py").read_text(encoding="utf-8"))
    top_level_calls = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]
    assert top_level_calls == []
    guards = [
        node
        for node in tree.body
        if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test)
    ]
    assert len(guards) == 1


@pytest.mark.parametrize("name", NAMES)
def test_examples_do_not_delete_profiles_or_print_endpoints(name: str) -> None:
    source = (EXAMPLES / f"{name}.py").read_text(encoding="utf-8")
    assert "hard_delete" not in source
    assert "websocket_debugging_url" not in source
    assert "raw_proxy" not in source


def test_only_async_entrypoints_call_asyncio_run() -> None:
    assert "asyncio.run(main())" in (EXAMPLES / "async_basic.py").read_text(encoding="utf-8")
    assert "asyncio.run(main())" in (EXAMPLES / "async_playwright.py").read_text(encoding="utf-8")
    assert "asyncio.run" not in (EXAMPLES / "sync_basic.py").read_text(encoding="utf-8")


def gpm_handler(events: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/profiles") and request.method == "GET":
            return json_response(
                {
                    "current_page": 1,
                    "per_page": 5,
                    "total": 1,
                    "last_page": 1,
                    "data": [{"id": "p1", "name": "First"}],
                }
            )
        if path.endswith("/profiles/p1"):
            return json_response({"id": "p1", "name": "First"})
        if "/profiles/start/" in path:
            events.append("start")
            return json_response(
                {
                    "profile_id": "p1",
                    "remote_debugging_port": 9222,
                    "websocket_debugging_url": SECRET_WS,
                }
            )
        if "/profiles/stop/" in path:
            events.append("stop")
            return json_response(None)
        return httpx.Response(500)

    return handler


def test_sync_and_async_basic_examples_give_the_same_lines() -> None:
    sync_events: list[str] = []
    with httpx.Client(transport=httpx.MockTransport(gpm_handler(sync_events))) as http:
        client = GPMClient(http_client=http)
        sync_lines = load("sync_basic").main(client=client, profile_id="p1")

    async_events: list[str] = []

    async def run_async() -> list[str]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(gpm_handler(async_events))
        ) as http:
            client = AsyncGPMClient(http_client=http)
            lines: list[str] = await load("async_basic").main(client=client, profile_id="p1")
            return lines

    async_lines = asyncio.run(run_async())
    assert sync_lines == async_lines
    assert sync_events == async_events == ["start", "stop"]
    assert "First" in "\n".join(sync_lines)
    assert SECRET_WS not in "\n".join(sync_lines)


class TitledPage(FakePage):
    def goto(self, url: str) -> None:
        self.url = url

    def title(self) -> str:
        return "Example Domain"


class AsyncTitledPage(TitledPage):
    async def goto(self, url: str) -> None:  # type: ignore[override]
        self.url = url

    async def title(self) -> str:  # type: ignore[override]
        return "Example Domain"


def test_sync_playwright_example_detaches_before_stop_and_reuses_the_context() -> None:
    events: list[str] = []
    pw, browser, context, _ = make_world("sync", events=events)
    context.pages = [TitledPage()]
    assert isinstance(context, FakeContext)
    with httpx.Client(transport=httpx.MockTransport(gpm_handler(events))) as http:
        client = GPMClient(http_client=http)
        lines = load("sync_playwright").main(client=client, profile_id="p1", playwright=pw)
    assert events == ["start", "detach", "stop"]
    assert context.new_page_calls == 0
    assert any("Example Domain" in line for line in lines)
    assert SECRET_WS not in "\n".join(lines)
    assert pw.stop_calls == 0


def test_async_playwright_example_detaches_before_stop_and_reuses_the_context() -> None:
    events: list[str] = []
    pw, browser, context, _ = make_world("async", events=events)
    context.pages = [AsyncTitledPage()]
    assert isinstance(context, AsyncFakeContext)

    async def run_async() -> list[str]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(gpm_handler(events))) as http:
            client = AsyncGPMClient(http_client=http)
            lines: list[str] = await load("async_playwright").main(
                client=client, profile_id="p1", playwright=pw
            )
            return lines

    lines = asyncio.run(run_async())
    assert events == ["start", "detach", "stop"]
    assert context.new_page_calls == 0
    assert any("Example Domain" in line for line in lines)


@pytest.mark.parametrize("name", ["sync_playwright", "async_playwright"])
def test_playwright_examples_require_a_profile_id(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GPM_PROFILE_ID", raising=False)
    module = load(name)
    with pytest.raises(SystemExit):
        result = module.main()
        if asyncio.iscoroutine(result):
            asyncio.run(result)
