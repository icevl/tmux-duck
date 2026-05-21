"""Tests for the embedded web server lifecycle."""

from __future__ import annotations

import asyncio

import pytest
import uvicorn

from codexbot import config as config_module
from codexbot.web.server import EmbeddedUvicornServer


async def _asgi_app(_scope: object, _receive: object, _send: object) -> None:
    return None


@pytest.mark.asyncio
async def test_embedded_uvicorn_server_does_not_capture_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = EmbeddedUvicornServer(uvicorn.Config(_asgi_app, lifespan="off"))
    calls: list[object] = []

    async def fake_serve(sockets: object | None = None) -> None:
        calls.append(sockets)

    def fail_capture_signals() -> None:
        raise AssertionError("embedded server must not capture process signals")

    monkeypatch.setattr(server, "_serve", fake_serve)
    monkeypatch.setattr(server, "capture_signals", fail_capture_signals)

    await server.serve()

    assert calls == [None]


@pytest.mark.asyncio
async def test_start_web_server_schedules_search_supervisor_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-02/T-02-01: search startup is scheduled without blocking web startup."""
    from codexbot.web import server as web_server

    monkeypatch.setattr(
        config_module.config, "web_ui_password", "hunter2", raising=False
    )
    monkeypatch.setattr(config_module.config, "web_ui_secret", "secret", raising=False)
    monkeypatch.setattr(config_module.config, "web_ui_enabled", True, raising=False)
    monkeypatch.setattr(
        config_module.config, "web_ui_totp_required", False, raising=False
    )
    monkeypatch.setattr(config_module.config, "web_ui_totp_secret", "", raising=False)
    monkeypatch.setattr(
        config_module.config, "auto_update_enabled", False, raising=False
    )

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_start_worker_if_needed() -> None:
        started.set()
        await release.wait()

    async def fake_serve(self: EmbeddedUvicornServer, sockets: object = None) -> None:
        await release.wait()

    async def fake_stream_pane_loop(_bus: object) -> None:
        await release.wait()

    monkeypatch.setattr(
        web_server.search_supervisor,
        "start_worker_if_needed",
        fake_start_worker_if_needed,
    )
    monkeypatch.setattr(EmbeddedUvicornServer, "_serve", fake_serve)
    monkeypatch.setattr(web_server, "stream_pane_loop", fake_stream_pane_loop)

    handle = await web_server.start_web_server(monitor=None, bot=None)

    assert handle is not None
    await asyncio.wait_for(started.wait(), timeout=1.0)

    release.set()
    await web_server.stop_web_server()
