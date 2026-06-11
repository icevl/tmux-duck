"""Minimal localhost HTTP server for the write-gate approval endpoint.

In headless mode (Telegram + web UI disabled) the Claude ``PreToolUse`` hook
still needs somewhere to POST tool calls. The full web UI hosts
``/api/connectors/approve-tool``; this is the standalone equivalent — a tiny
aiohttp app bound to loopback, sharing the same decision logic and shared
secret. Codex connectors don't need it (their gate is pane-based).
"""

from __future__ import annotations

import logging
import secrets

from aiohttp import web

from .approval import approval_secret, decide_tool_call

logger = logging.getLogger(__name__)


async def _handle(request: web.Request) -> web.Response:
    provided = request.headers.get("X-Connector-Secret", "")
    if not provided or not secrets.compare_digest(provided, approval_secret()):
        return web.json_response({"error": "forbidden"}, status=403)
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        payload = {}
    return web.json_response(await decide_tool_call(payload))


class ApprovalServer:
    """Loopback HTTP server hosting POST /api/connectors/approve-tool."""

    def __init__(self, port: int, host: str = "127.0.0.1") -> None:
        self._host = host
        self._port = port
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/api/connectors/approve-tool", _handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info("Approval server listening on http://%s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None


__all__ = ["ApprovalServer"]
