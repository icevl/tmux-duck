"""Boots and supervises the enabled connectors inside the bot loop.

The manager is a process-wide singleton (:data:`connector_manager`). On
:meth:`start` it loads every enabled :class:`ConnectorRecord`, instantiates
the matching connector class, and starts it. :meth:`reload` re-syncs a
single connector after its config changes in the web UI, so enabling or
disabling a connector takes effect without restarting the process.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING, Any

from . import store
from .base import BaseConnector, ConnectorContext, get_connector_class

if TYPE_CHECKING:
    from ..session_monitor import SessionMonitor

logger = logging.getLogger(__name__)

# Infrastructure modules in this package that are not connectors and must
# not be auto-imported as ones.
_INFRA_MODULES = {
    "base",
    "store",
    "manager",
    "bridge",
    "classifier",
    "approval",
}


def _load_connector_implementations() -> None:
    """Auto-discover connector modules so their type decorators register.

    Drop-in: any new ``connectors/<name>.py`` defining a
    ``@register_connector_type``-decorated class is picked up with no edits
    here. Import is guarded per-module — a connector whose optional dependency
    is missing (e.g. ``slack_bolt`` not installed) is skipped, not fatal.
    """
    import codexbot.connectors as pkg

    for module in pkgutil.iter_modules(pkg.__path__):
        if module.name in _INFRA_MODULES:
            continue
        try:
            importlib.import_module(f"{pkg.__name__}.{module.name}")
        except ImportError as exc:
            logger.info("Connector module %s unavailable: %s", module.name, exc)
        except Exception:  # noqa: BLE001
            logger.exception("Failed importing connector module %s", module.name)


class ConnectorManager:
    """Owns the lifecycle of all configured connectors."""

    def __init__(self) -> None:
        self._ctx: ConnectorContext | None = None
        self._connectors: dict[str, BaseConnector] = {}
        self._lock = asyncio.Lock()
        self._started = False

    async def start(
        self, monitor: "SessionMonitor | None" = None, bot: Any = None
    ) -> None:
        """Load and start every enabled connector."""
        async with self._lock:
            if self._started:
                logger.warning("ConnectorManager already started")
                return
            _load_connector_implementations()
            self._ctx = ConnectorContext(monitor=monitor, bot=bot)
            self._started = True
            from ..config import config

            records = store.list_connectors(enabled_only=True)
            if records and not config.web_ui_enabled and config.telegram_enabled:
                # The Claude write-gate posts approvals to the FastAPI
                # endpoint; in Telegram mode with the Web UI off there is no
                # server, so the hook fails open (writes run un-gated). Codex's
                # pane gate is unaffected. (Headless mode runs its own
                # loopback approval server, so this doesn't apply there.)
                logger.warning(
                    "Connectors enabled but Web UI is disabled — the Claude "
                    "write-gate is unavailable and Claude writes will NOT be "
                    "gated. Set WEB_UI_PASSWORD to enable approvals."
                )
            for record in records:
                await self._start_one(record)
            # Hide any pre-existing connector windows from the web/TG lists.
            from . import bridge

            bridge.tag_connector_windows()
            logger.info("ConnectorManager started (%d active)", len(self._connectors))

    async def stop(self) -> None:
        """Stop all running connectors."""
        async with self._lock:
            if not self._started:
                return
            for connector in list(self._connectors.values()):
                await self._stop_instance(connector)
            self._connectors.clear()
            self._started = False
            self._ctx = None
            logger.info("ConnectorManager stopped")

    async def reload(self, connector_id: str) -> None:
        """Re-sync a single connector to its current persisted state.

        Stops the running instance (if any), then starts it again when the
        record exists and is enabled. Used after web-UI create/update/delete
        so changes apply live.
        """
        async with self._lock:
            if not self._started:
                return
            existing = self._connectors.pop(connector_id, None)
            if existing is not None:
                await self._stop_instance(existing)
            record = store.get_connector(connector_id)
            if record is not None and record.enabled:
                await self._start_one(record)

    def is_running(self, connector_id: str) -> bool:
        return connector_id in self._connectors

    def get_connector(self, connector_id: str) -> BaseConnector | None:
        return self._connectors.get(connector_id)

    async def _start_one(self, record: store.ConnectorRecord) -> None:
        cls = get_connector_class(record.type)
        if cls is None:
            logger.warning(
                "No connector implementation for type=%s (id=%s); skipping",
                record.type,
                record.id,
            )
            return
        assert self._ctx is not None
        try:
            connector = cls(record, self._ctx)
            await connector.start()
        except Exception:
            logger.exception("Failed to start connector id=%s", record.id)
            return
        self._connectors[record.id] = connector
        logger.info("Connector started id=%s type=%s", record.id, record.type)

    async def _stop_instance(self, connector: BaseConnector) -> None:
        try:
            await connector.stop()
        except Exception:
            logger.exception("Error stopping connector id=%s", connector.id)


connector_manager = ConnectorManager()


__all__ = ["ConnectorManager", "connector_manager"]
