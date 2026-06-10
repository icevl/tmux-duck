"""Connector base class, runtime context, and type registry.

A connector is constructed from its persisted :class:`ConnectorRecord`
plus a :class:`ConnectorContext` that hands it the shared session monitor
and (optionally) the Telegram bot. Concrete connectors (e.g. Slack)
register themselves with :func:`register_connector_type` so the manager
can instantiate them by ``type`` string without importing each module.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Callable

from .store import ConnectorRecord

if TYPE_CHECKING:
    from ..session_monitor import SessionMonitor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfigField:
    """One declarative config field, rendered generically by the web UI.

    ``type`` selects the widget: ``text`` | ``secret`` | ``textarea`` |
    ``runtime`` (agent picker) | ``directory`` (folder picker) | ``list``
    (comma-separated → array) | ``bool``. Secret fields are masked in API
    responses and preserved when left blank on edit.
    """

    key: str
    label: str
    type: str = "text"
    required: bool = False
    placeholder: str = ""
    help: str = ""


@dataclass
class ConnectorContext:
    """Shared services handed to every connector at construction.

    ``monitor`` is the live :class:`SessionMonitor`; connectors subscribe
    to it to stream agent output back to their external surface. ``bot``
    is the Telegram bot when available (kept for parity / future mirroring)
    and may be ``None``.
    """

    monitor: "SessionMonitor | None" = None
    bot: Any = None


class BaseConnector(ABC):
    """Lifecycle interface shared by all connectors."""

    # Human-readable type name shown in the web UI's "Add" picker.
    type_label: str = ""

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        """Declarative config fields the web UI renders a form from.

        Override per connector. The universal ``name`` and ``enabled`` fields
        are handled by the UI outside this schema.
        """
        return []

    def __init__(self, record: ConnectorRecord, ctx: ConnectorContext) -> None:
        self._record = record
        self._ctx = ctx

    @property
    def id(self) -> str:
        return self._record.id

    @property
    def type(self) -> str:
        return self._record.type

    @property
    def name(self) -> str:
        return self._record.name

    @property
    def config(self) -> dict[str, Any]:
        return self._record.config

    @property
    def record(self) -> ConnectorRecord:
        return self._record

    @abstractmethod
    async def start(self) -> None:
        """Open the external connection and begin handling inbound traffic."""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """Tear down the external connection and any background tasks."""
        raise NotImplementedError

    async def request_write_approval(
        self, window_id: str, title: str, detail: str
    ) -> bool:
        """Ask the external surface to approve a mutating operation.

        Returns ``True`` to allow, ``False`` to deny. The default allows
        (no interactive surface); connectors that can prompt a human (Slack)
        override this to block until the user decides.
        """
        return True


# --- type registry ---------------------------------------------------------

CONNECTOR_TYPES: dict[str, type[BaseConnector]] = {}


def register_connector_type(
    type_name: str,
) -> Callable[[type[BaseConnector]], type[BaseConnector]]:
    """Class decorator registering a connector implementation by type."""

    def _register(cls: type[BaseConnector]) -> type[BaseConnector]:
        CONNECTOR_TYPES[type_name] = cls
        return cls

    return _register


def get_connector_class(type_name: str) -> type[BaseConnector] | None:
    return CONNECTOR_TYPES.get(type_name)


def list_connector_types() -> list[dict[str, Any]]:
    """Serializable descriptors of every registered connector type + schema."""
    out: list[dict[str, Any]] = []
    for type_name, cls in sorted(CONNECTOR_TYPES.items()):
        out.append(
            {
                "type": type_name,
                "label": cls.type_label or type_name,
                "fields": [asdict(f) for f in cls.config_schema()],
            }
        )
    return out


def secret_keys_for_type(type_name: str) -> tuple[str, ...]:
    """Config keys marked as secret for a type (masked + preserve-on-blank)."""
    cls = CONNECTOR_TYPES.get(type_name)
    if cls is None:
        return ()
    return tuple(f.key for f in cls.config_schema() if f.type == "secret")


__all__ = [
    "BaseConnector",
    "ConfigField",
    "ConnectorContext",
    "ConnectorRecord",
    "CONNECTOR_TYPES",
    "get_connector_class",
    "list_connector_types",
    "register_connector_type",
    "secret_keys_for_type",
]
