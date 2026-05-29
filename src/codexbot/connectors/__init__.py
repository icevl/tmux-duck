"""External input connectors (Slack, …) layered over the session core.

A connector is a transport: it turns inbound messages from an external
chat surface into session input, and streams agent output back out. The
Telegram bot and the web UI are the two pre-existing transports; this
package generalizes the pattern so new sources (Slack first) can be added
without touching the tmux/session/runtime core.

Connector configuration (credentials, custom instructions, default agent,
working directory, approval policy) lives in ``~/.codexbot/connectors.sqlite``
and is managed from the web UI. The :class:`ConnectorManager` boots the
enabled connectors inside the bot's asyncio loop.
"""

from __future__ import annotations

from .base import BaseConnector, ConnectorContext, ConnectorRecord
from .manager import ConnectorManager, connector_manager

__all__ = [
    "BaseConnector",
    "ConnectorContext",
    "ConnectorRecord",
    "ConnectorManager",
    "connector_manager",
]
