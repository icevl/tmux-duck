# Phase 01: Search Contract and Status Surface - Pattern Map

**Mapped:** 2026-05-21
**Files analyzed:** 8
**Analogs found:** 8 / 8

## Scope Guard

Phase 1 is backend contract/status only. The planner should not map or implement
LanceDB, worker process supervision, embedding/model imports, live queue
draining, retrieval ranking, snippets, or Web UI search rendering in this phase.

`web-ui/src/api.ts` is intentionally not mapped here: frontend API typing may be
added later only if the approved plan explicitly needs it, but this pattern map
stays on the backend status/contract surface.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/codexbot/search/__init__.py` | config | transform | `src/codexbot/runtimes/__init__.py` | role-match |
| `src/codexbot/search/contracts.py` | model | transform, request-response | `src/codexbot/web/api.py` | role-match |
| `src/codexbot/search/state.py` | utility | file-I/O, config | `src/codexbot/utils.py` | exact |
| `src/codexbot/search/client.py` | service | request-response | `src/codexbot/web/update_checker.py` | role-match |
| `src/codexbot/web/api.py` | controller | request-response | `src/codexbot/web/api.py` | exact |
| `tests/codexbot/test_search_contracts.py` | test | transform, request-response | `tests/codexbot/test_transcript_parser.py` | role-match |
| `tests/codexbot/test_search_state.py` | test | file-I/O | `tests/codexbot/test_utils.py` | exact |
| `tests/codexbot/test_web_api.py` | test | request-response | `tests/codexbot/test_web_api.py` | exact |

## Pattern Assignments

### `src/codexbot/search/__init__.py` (config, transform)

**Analog:** `src/codexbot/runtimes/__init__.py`

**Imports pattern** (lines 12-17):
```python
from __future__ import annotations

from .base import AgentRuntime
from .claude import ClaudeRuntime
from .codex import CodexRuntime
```

**Public exports pattern** (lines 43-50):
```python
__all__ = [
    "AgentRuntime",
    "CodexRuntime",
    "ClaudeRuntime",
    "DEFAULT_RUNTIME_NAME",
    "get_runtime",
    "all_runtimes",
]
```

**Apply to search package:** export only lightweight contract/client/state names
from `src/codexbot/search/__init__.py`. Do not import worker, LanceDB, torch,
transformers, sentence-transformers, FastEmbed, or indexing implementation
modules from package init.

---

### `src/codexbot/search/contracts.py` (model, transform/request-response)

**Analog:** `src/codexbot/web/api.py`

**Supporting analogs:** `src/codexbot/transcript_parser.py`,
`src/codexbot/session_monitor.py`, `src/codexbot/session.py`

**Imports pattern** (`src/codexbot/web/api.py` lines 31-58):
```python
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field
```

For `contracts.py`, copy the project style but keep imports narrower:
`from __future__ import annotations`, `typing.Literal` or `typing.Any` as
needed, and `from pydantic import BaseModel, Field`.

**Pydantic request/body model pattern** (`src/codexbot/web/api.py` lines 93-132):
```python
class LoginRequest(BaseModel):
    password: str
    totp_code: str | None = None


class CreateSessionRequest(BaseModel):
    cwd: str
    runtime: str = "codex"
    resume_session_id: str | None = None
    name: str | None = None


class PatchSessionRequest(BaseModel):
    """PATCH /api/sessions/{wid} body. At least one field must be supplied."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    pinned: bool | None = None


class ReorderSessionsRequest(BaseModel):
    """PATCH /api/sessions/order body."""

    window_ids: list[str] = Field(min_length=1, max_length=500)
```

Use this for `SearchRequest`, status DTOs, hit DTOs, provenance DTOs, generation
metadata, row identity, and routing metadata. Bound user input with `Field`,
especially search query length and requested result limits.

**Runtime-neutral provenance source** (`src/codexbot/transcript_parser.py`
lines 33-54):
```python
@dataclass
class ParsedEntry:
    """A single parsed message entry ready for display."""

    role: str  # "user" | "assistant"
    text: str  # Already formatted text
    content_type: (
        str  # "text" | "thinking" | "tool_use" | "tool_result" | "local_command"
    )
    tool_use_id: str | None = None
    timestamp: str | None = None  # ISO timestamp from JSONL
    tool_name: str | None = (
        None  # For tool_use entries, the tool name (e.g. "AskUserQuestion")
    )
    tool_input: dict[str, Any] | None = (
        None  # For tool_use entries, the decoded input payload
    )
    image_data: list[tuple[str, bytes]] | None = (
        None  # For tool_result entries with images: (media_type, raw_bytes)
    )
    transcript_offset: int | None = None
    transcript_index: int | None = None
```

**Transcript order pattern** (`src/codexbot/transcript_parser.py` lines 116-127):
```python
def _stamp_transcript_order(
    result: list[ParsedEntry],
    start_index: int,
    transcript_offset: int | None,
) -> None:
    if transcript_offset is None:
        return
    for transcript_index, entry in enumerate(result[start_index:]):
        if entry.transcript_offset is None:
            entry.transcript_offset = transcript_offset
        if entry.transcript_index is None:
            entry.transcript_index = transcript_index
```

**Live normalized message fields** (`src/codexbot/session_monitor.py` lines
47-66):
```python
@dataclass
class NewMessage:
    """A new message detected by the monitor."""

    session_id: str
    text: str
    is_complete: bool
    message_type: Literal["content", "completion"] = "content"
    turn_id: int | None = None
    is_stale_turn: bool = False
    turn_had_visible_output: bool = False
    content_type: str = "text"
    tool_use_id: str | None = None
    role: str = "assistant"
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    image_data: list[tuple[str, bytes]] | None = None
    timestamp: str | None = None
    transcript_offset: int | None = None
    transcript_index: int | None = None
```

**Mutable routing metadata source** (`src/codexbot/session.py` lines 65-88):
```python
@dataclass
class WindowState:
    """Persistent state for a tmux window."""

    session_id: str = ""
    cwd: str = ""
    window_name: str = ""
    runtime: str = "codex"
    pinned: bool = False
    sort_order: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "runtime": self.runtime,
        }
        if self.window_name:
            data["window_name"] = self.window_name
        if self.pinned:
            data["pinned"] = True
        if self.sort_order is not None:
            data["sort_order"] = self.sort_order
        return data
```

**Apply to search contracts:** keep `SearchRowIdentity` derived from runtime,
transcript source, transcript offset/index, content type, optional tool fields,
and chunk index. Keep `window_id`, `cwd`, display name, pinned, status, and
sort metadata in a separate routing/display DTO only.

---

### `src/codexbot/search/state.py` (utility, file-I/O/config)

**Analog:** `src/codexbot/utils.py`

**Imports and env helper pattern** (lines 10-23):
```python
import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any

CODEXBOT_DIR_ENV = "CODEXBOT_DIR"


def codexbot_dir() -> Path:
    """Resolve config directory from CODEXBOT_DIR env var or default ~/.codexbot."""
    raw = os.environ.get(CODEXBOT_DIR_ENV, "")
    return Path(raw).expanduser() if raw else Path.home() / ".codexbot"
```

**Atomic JSON pattern for future metadata writes** (lines 26-51):
```python
def atomic_write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Write JSON data to a file atomically.

    Writes to a temporary file in the same directory, then renames it
    to the target path. This prevents data corruption if the process
    is interrupted mid-write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=indent)

    # Write to temp file in same directory (same filesystem for atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=f".{path.name}."
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

**Existing authoritative state boundary** (`src/codexbot/config.py` lines
253-255):
```python
# State files under config_dir.
self.state_file = self.config_dir / "state.json"
self.monitor_state_file = self.config_dir / "monitor_state.json"
```

**Monitor state save pattern to avoid for search** (`src/codexbot/monitor_state.py`
lines 72-90):
```python
def save(self) -> None:
    """Save state to file atomically."""
    from .utils import atomic_write_json

    data = {
        "tracked_sessions": {
            k: v.to_dict() for k, v in self.tracked_sessions.items()
        }
    }

    try:
        atomic_write_json(self.state_file, data)
        self._dirty = False
        logger.debug(
            "Saved %d tracked sessions to state", len(self.tracked_sessions)
        )
    except OSError as e:
        logger.error("Failed to save state file: %s", e)
```

**Apply to search state:** implement `search_dir()` as
`codexbot_dir() / "search"` and keep search-owned state under that namespace.
Do not import or write `config.monitor_state_file`; tests must prove
`monitor_state.json` remains unchanged.

---

### `src/codexbot/search/client.py` (service, request-response)

**Analog:** `src/codexbot/web/update_checker.py`

**Imports and lightweight service state pattern** (lines 17-29, 37-53):
```python
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, TypedDict

from .events import EventBus

logger = logging.getLogger(__name__)


class UpdateStatus(TypedDict):
    current_sha: str | None
    latest_sha: str | None
    has_update: bool
    dirty: bool
    subject: str | None


# Process-global cache: REST status endpoint reads this; the poll loop
# updates it. Plain dict is fine — single asyncio loop, no concurrency.
_state: UpdateStatus = {
    "current_sha": None,
    "latest_sha": None,
    "has_update": False,
    "dirty": False,
    "subject": None,
}
```

For search, use Pydantic contracts instead of `TypedDict` where possible, but
copy the lightweight dependency style: the request path can read status through
a cheap provider without model/index imports.

**Service status accessor pattern** (lines 159-160):
```python
def get_status() -> UpdateStatus:
    return dict(_state)  # type: ignore[return-value]
```

**Transient failure behavior pattern** (lines 119-126):
```python
async def tick(bus: EventBus) -> None:
    """One poll iteration. Publishes the WS event on rising edge only."""
    current = await asyncio.to_thread(get_local_sha)
    dirty = await asyncio.to_thread(is_dirty)
    remote = await _fetch_remote()
    if remote is None:
        # Network blip — leave previous state alone; the next tick retries.
        return
```

**Apply to search client:** expose cheap `get_status()` and `search(req)`
functions or a tiny provider class that returns typed `missing` or
`unavailable`/empty responses in Phase 1. Normal first-run/not-ready states are
successful typed responses, not raised `HTTPException`s.

---

### `src/codexbot/web/api.py` (controller, request-response)

**Analog:** `src/codexbot/web/api.py`

**Import boundary pattern** (lines 43-80):
```python
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import config
from ..runtimes import all_runtimes, get_runtime
from ..session import session_manager
from ..skill_hints import skill_hint_registry
from ..slash_commands import slash_command_registry
from ..skills import discover_skills
from ..tmux_manager import tmux_manager
from ..utils import codexbot_dir
```

When adding search routes, only import lightweight `codexbot.search.contracts`,
`codexbot.search.client`, and `codexbot.search.state` pieces. Do not import
LanceDB, torch, transformers, sentence-transformers, FastEmbed, worker modules,
or retrieval/ranking modules in `web/api.py`.

**Auth dependency pattern** (lines 460-467):
```python
async def require_auth(request: Request) -> str:
    cookie = request.cookies.get(COOKIE_NAME)
    subject = auth.verify_cookie(cookie)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized"
        )
    return subject
```

**Authenticated GET route pattern** (lines 568-603):
```python
@app.get("/api/sessions")
async def list_sessions(_user: str = Depends(require_auth)) -> dict[str, Any]:
    windows = await tmux_manager.list_windows()
    # Make sure the transcript mtime index is current so the sort by
    # activity reflects reality.
    await session_manager._refresh_sessions_index(force=True)
    result: list[dict[str, Any]] = []
    for w in windows:
        ws = session_manager.get_window_state(w.window_id)
        runtime_name = ws.runtime or "codex"
        display_name = (
            session_manager.get_display_name(w.window_id) or w.window_name
        )
        last_activity: float | None = None
        if ws.session_id:
            mtime = session_manager._session_mtime_index.get(ws.session_id)
            if mtime:
                last_activity = mtime
        result.append(
            {
                "window_id": w.window_id,
                "name": display_name,
                "tmux_name": w.window_name,
                "cwd": ws.cwd or w.cwd,
                "runtime": runtime_name,
                "session_id": ws.session_id or None,
                "pane_command": w.pane_current_command,
                "last_activity": last_activity,
                "pinned": bool(ws.pinned),
                "sort_order": ws.sort_order,
            }
        )
    # Pinned sessions float to the top; manual order wins inside each
    # group, with activity/name as the stable fallback for older state.
    result.sort(key=_session_summary_sort_key)
    return {"sessions": result}
```

Search routes should use current tmux/session data at request time for open
session routing/display metadata. Do not bake `window_id`, cwd, pinned, sort
order, or display names into indexed row identity.

**Query-bound validation pattern** (lines 759-769):
```python
@app.get("/api/sessions/{window_id}/messages")
async def get_messages(
    window_id: str,
    limit: int = Query(500, ge=1, le=2000),
    before: str | None = Query(None),
    after: str | None = Query(None),
    before_offset: int | None = Query(None, ge=0),
    before_index: int | None = Query(None, ge=0),
    after_offset: int | None = Query(None, ge=0),
    after_index: int | None = Query(None, ge=0),
    _user: str = Depends(require_auth),
) -> dict[str, Any]:
```

Use this style for `GET /api/search/status` and `POST /api/search`: auth is
mandatory, request limits are bounded, and not-ready search states return typed
200 bodies.

**Status endpoint pattern** (lines 1328-1332):
```python
@app.get("/api/update/status")
async def update_status(_user: str = Depends(require_auth)) -> dict[str, Any]:
    status = dict(get_update_status())
    status["enabled"] = config.auto_update_enabled
    return status
```

---

### `tests/codexbot/test_search_contracts.py` (test, transform/request-response)

**Analog:** `tests/codexbot/test_transcript_parser.py`

**Supporting analog:** `tests/codexbot/test_session.py`

**Transcript order assertion pattern** (`tests/codexbot/test_transcript_parser.py`
lines 369-384):
```python
def test_transcript_order_metadata(self, make_jsonl_entry, make_text_block):
    first = make_jsonl_entry(
        "assistant", [make_text_block("one"), make_text_block("two")]
    )
    first[TranscriptParser.TRANSCRIPT_OFFSET_KEY] = 42
    second = make_jsonl_entry("user", [make_text_block("three")])
    second[TranscriptParser.TRANSCRIPT_OFFSET_KEY] = 99

    result, pending = TranscriptParser.parse_entries([first, second])

    assert pending == {}
    assert [(e.text, e.transcript_offset, e.transcript_index) for e in result] == [
        ("one", 42, 0),
        ("two", 42, 1),
        ("three", 99, 0),
    ]
```

**Mutable metadata validation pattern** (`tests/codexbot/test_session.py` lines
165-176):
```python
def test_sort_order_round_trips_when_valid(self) -> None:
    state = WindowState(session_id="abc", cwd="/tmp", sort_order=7)

    restored = WindowState.from_dict(state.to_dict())

    assert restored.sort_order == 7

@pytest.mark.parametrize("value", [-1, "3", True, None])
def test_invalid_sort_order_loads_as_none(self, value: object) -> None:
    state = WindowState.from_dict({"sort_order": value})

    assert state.sort_order is None
```

**Apply to search contract tests:** assert required provenance fields exist,
row/chunk identity includes transcript provenance and chunk index, and row
identity excludes `window_id`, cwd, display name, pinned, sort order, and other
mutable routing/display fields. Add a static import-boundary test that reads
`src/codexbot/web/api.py` and lightweight search modules and rejects forbidden
strings: `lancedb`, `torch`, `transformers`, `sentence_transformers`,
`sentence-transformers`, `fastembed`, and worker/index implementation imports.

---

### `tests/codexbot/test_search_state.py` (test, file-I/O)

**Analog:** `tests/codexbot/test_utils.py`

**Supporting analog:** `tests/codexbot/test_monitor_state.py`

**Env-dir helper test pattern** (`tests/codexbot/test_utils.py` lines 11-18):
```python
class TestCodexbotDir:
    def test_returns_env_var_path(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CODEXBOT_DIR", "/custom/config")
        assert codexbot_dir() == Path("/custom/config")

    def test_returns_default_without_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("CODEXBOT_DIR", raising=False)
        assert codexbot_dir() == Path.home() / ".codexbot"
```

**File creation and round-trip pattern** (`tests/codexbot/test_utils.py` lines
21-44):
```python
class TestAtomicWriteJson:
    def test_writes_valid_json(self, tmp_path: Path):
        target = tmp_path / "data.json"
        atomic_write_json(target, {"key": "value"})
        result = json.loads(target.read_text(encoding="utf-8"))
        assert result == {"key": "value"}

    def test_creates_parent_directories(self, tmp_path: Path):
        target = tmp_path / "a" / "b" / "c" / "data.json"
        atomic_write_json(target, [1, 2, 3])
        assert target.exists()
        assert json.loads(target.read_text(encoding="utf-8")) == [1, 2, 3]

    def test_round_trip(self, tmp_path: Path):
        data = {"users": [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]}
        target = tmp_path / "round_trip.json"
        atomic_write_json(target, data)
        assert json.loads(target.read_text(encoding="utf-8")) == data

    def test_no_temp_files_left_on_success(self, tmp_path: Path):
        target = tmp_path / "clean.json"
        atomic_write_json(target, {"ok": True})
        remaining = list(tmp_path.glob(".*tmp*"))
        assert remaining == []
```

**Monkeypatch write isolation pattern** (`tests/codexbot/test_monitor_state.py`
lines 60-78):
```python
class TestMonitorStateSave:
    def test_save_writes_via_atomic_write(self, tmp_path, monkeypatch):
        state_file = tmp_path / "state.json"
        state = MonitorState(state_file=state_file)
        state.update_session(
            TrackedSession(session_id="s1", file_path="/a.jsonl", last_byte_offset=10)
        )
        calls: list[tuple] = []

        def fake_write(path, data, indent=2):
            calls.append((path, data))

        monkeypatch.setattr("codexbot.utils.atomic_write_json", fake_write)
        state.save()
        assert len(calls) == 1
        path, data = calls[0]
        assert path == state_file
        assert "s1" in data["tracked_sessions"]
        assert data["tracked_sessions"]["s1"]["last_byte_offset"] == 10
```

**Apply to search state tests:** set `CODEXBOT_DIR` to `tmp_path`, assert
`search_dir()` resolves to `tmp_path / "search"`, and prove calling Phase 1
status/search helpers does not create or mutate `tmp_path / "monitor_state.json"`.

---

### `tests/codexbot/test_web_api.py` (test, request-response)

**Analog:** `tests/codexbot/test_web_api.py`

**Fixture pattern** (lines 58-75):
```python
@pytest.fixture
def web_password(monkeypatch: pytest.MonkeyPatch) -> str:
    _baseline_config(monkeypatch)
    return "hunter2"


@pytest.fixture
def client(web_password: str) -> TestClient:
    bus = EventBus()
    app = create_app(bus)
    return TestClient(app)


@pytest.fixture
def authed_client(client: TestClient, web_password: str) -> TestClient:
    r = client.post("/api/login", json={"password": web_password})
    assert r.status_code == 200
    return client
```

**Auth gate test pattern** (lines 102-104):
```python
def test_protected_endpoint_requires_auth(client: TestClient) -> None:
    r = client.get("/api/sessions")
    assert r.status_code == 401
```

**Authenticated GET response-shape pattern** (lines 107-132):
```python
def test_list_sessions_returns_windows(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_windows = [
        TmuxWindow(
            window_id="@5",
            window_name="codexbot",
            cwd="/tmp",
            pane_current_command="codex",
        ),
    ]

    async def fake_list() -> list[TmuxWindow]:
        return fake_windows

    from codexbot.web import api as web_api

    monkeypatch.setattr(web_api.tmux_manager, "list_windows", fake_list)

    r = authed_client.get("/api/sessions")
    assert r.status_code == 200
    body = r.json()
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["window_id"] == "@5"
    assert body["sessions"][0]["runtime"] in {"codex", "claude"}
    assert "sort_order" in body["sessions"][0]
```

**Authenticated POST body pattern** (lines 525-540):
```python
def test_send_text(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []

    async def fake_send(wid: str, text: str) -> tuple[bool, str]:
        calls.append((wid, text))
        return True, "sent"

    from codexbot.web import api as web_api

    monkeypatch.setattr(web_api.session_manager, "send_to_window", fake_send)

    r = authed_client.post(
        "/api/sessions/@5/text", json={"text": "hello world", "enter": True}
    )
    assert r.status_code == 200, r.text
```

**Apply to web API tests:** add unauthenticated tests for
`GET /api/search/status` and `POST /api/search`, plus authenticated tests that
assert typed 200 not-ready responses. The response should include the lifecycle
state vocabulary and should not expose raw transcript content, local secrets, or
model/import details.

## Shared Patterns

### Authentication

**Source:** `src/codexbot/web/api.py` lines 460-467

**Apply to:** `GET /api/search/status`, `POST /api/search`

```python
async def require_auth(request: Request) -> str:
    cookie = request.cookies.get(COOKIE_NAME)
    subject = auth.verify_cookie(cookie)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized"
        )
    return subject
```

### Pydantic Validation

**Source:** `src/codexbot/web/api.py` lines 105-132

**Apply to:** search request DTO, status DTOs, provenance DTOs, routing DTOs,
generation metadata DTOs

```python
class PatchSessionRequest(BaseModel):
    """PATCH /api/sessions/{wid} body. At least one field must be supplied."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    pinned: bool | None = None


class ReorderSessionsRequest(BaseModel):
    """PATCH /api/sessions/order body."""

    window_ids: list[str] = Field(min_length=1, max_length=500)
```

### Transcript Provenance

**Source:** `src/codexbot/transcript_parser.py` lines 33-54 and
`src/codexbot/session_monitor.py` lines 47-66

**Apply to:** `TranscriptProvenance`, `SearchRowIdentity`, hit/source DTOs

```python
role: str  # "user" | "assistant"
content_type: (
    str  # "text" | "thinking" | "tool_use" | "tool_result" | "local_command"
)
tool_use_id: str | None = None
timestamp: str | None = None  # ISO timestamp from JSONL
tool_name: str | None = (
    None  # For tool_use entries, the tool name (e.g. "AskUserQuestion")
)
transcript_offset: int | None = None
transcript_index: int | None = None
```

### Routing Metadata Is Not Identity

**Source:** `src/codexbot/session.py` lines 65-88 and
`src/codexbot/web/api.py` lines 568-603

**Apply to:** search row identity, routing metadata DTO, tests

```python
"window_id": w.window_id,
"name": display_name,
"tmux_name": w.window_name,
"cwd": ws.cwd or w.cwd,
"runtime": runtime_name,
"session_id": ws.session_id or None,
"pane_command": w.pane_current_command,
"last_activity": last_activity,
"pinned": bool(ws.pinned),
"sort_order": ws.sort_order,
```

Use those fields only as current request-time routing/display metadata.

### Search State Namespace

**Source:** `src/codexbot/utils.py` lines 20-23 and `src/codexbot/config.py`
lines 253-255

**Apply to:** `src/codexbot/search/state.py`, `tests/codexbot/test_search_state.py`

```python
def codexbot_dir() -> Path:
    """Resolve config directory from CODEXBOT_DIR env var or default ~/.codexbot."""
    raw = os.environ.get(CODEXBOT_DIR_ENV, "")
    return Path(raw).expanduser() if raw else Path.home() / ".codexbot"
```

`search_dir()` should be derived as `codexbot_dir() / "search"`.

### Typed Not-Ready Responses

**Source:** `src/codexbot/web/api.py` lines 1328-1332 and
`src/codexbot/web/update_checker.py` lines 159-160

**Apply to:** search status route and search stub route

```python
@app.get("/api/update/status")
async def update_status(_user: str = Depends(require_auth)) -> dict[str, Any]:
    status = dict(get_update_status())
    status["enabled"] = config.auto_update_enabled
    return status
```

Return typed 200 status bodies for `missing`, `building`, `partial`, `ready`,
`stale`, `degraded`, and `unavailable`. Use real HTTP errors only for transport,
auth, validation, or unexpected server failures.

### Import Boundary

**Source:** `src/codexbot/web/api.py` lines 43-80

**Apply to:** `src/codexbot/web/api.py`, `src/codexbot/search/__init__.py`,
`src/codexbot/search/client.py`, static tests

Forbidden in Phase 1 request-path modules:

```text
lancedb
torch
transformers
sentence_transformers
sentence-transformers
fastembed
search worker/index/retrieval/ranking modules
```

### Test Style

**Source:** `tests/codexbot/test_web_api.py` lines 58-75,
`tests/codexbot/test_utils.py` lines 11-18

**Apply to:** all Phase 1 tests

Use local fixtures, `tmp_path`, `monkeypatch`, direct `TestClient` calls, and
explicit response JSON assertions. Avoid live tmux, transcript filesystem, model
runtime, or network dependencies in Phase 1 tests.

## No Analog Found

None.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| N/A | N/A | N/A | All Phase 1 backend contract/status files have close existing analogs. |

## Out Of Scope For This Phase

| Area | Reason |
|------|--------|
| LanceDB tables and writes | Later index/storage phase; explicitly excluded from Phase 1. |
| Embeddings/model imports | Violates FastAPI request-handler import boundary for Phase 1. |
| Worker process, leases, backfill, live queue | Later worker/index phases. |
| Retrieval ranking/snippets | Later query execution phase. |
| Web UI search rendering | User scope is backend contract/status only. |
| Telegram search surface | Not in Phase 1 scope. |

## Metadata

**Analog search scope:** `src/codexbot`, `tests/codexbot`, `web-ui/src` for
scope exclusion, plus phase artifacts in
`.planning/phases/01-search-contract-and-status-surface/`.

**Files scanned:** 72 files from `rg --files src/codexbot tests/codexbot`; 66
Python source/test files from `find src/codexbot tests/codexbot -name '*.py'`.

**Project skills:** `.codex/skills/` and `.agents/skills/` are absent in this
repo.

**Pattern extraction date:** 2026-05-21
