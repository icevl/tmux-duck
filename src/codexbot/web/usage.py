"""Local agent usage counters for the web sidebar.

Both agent CLIs already write their usage to disk, so the sidebar counters are
built purely from local files — no provider API calls, which means polling can
never hit a rate limit (429), no matter the cadence:

  * **Codex** rollout files (``~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl``)
    carry ``token_count`` events with an official ``rate_limits`` snapshot —
    the exact 5h/weekly ``used_percent`` numbers ``/status`` shows. We read the
    tail of the newest rollout and take the last snapshot.
  * **Claude Code** transcripts carry a ``usage`` object on every assistant
    message. Official limit percentages are NOT stored locally (they live
    behind an OAuth endpoint), so for Claude we aggregate token totals instead:
    today and the trailing 5h window. Parsing is incremental (per-file offset)
    and usage lines are deduped by ``message.id`` — one message is written as
    several lines (one per content block), each repeating the same usage.

A background publisher pushes an ``agent_usage`` event on the bus whenever the
visible numbers change; ``GET /api/usage`` serves the snapshot for the initial
render. Work is skipped entirely while no web client is attached.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from ..config import config

if TYPE_CHECKING:
    from .events import EventBus

logger = logging.getLogger(__name__)

# Poll cadence while a web client is attached.
POLL_INTERVAL_SECONDS = 120.0
# Cheap re-check cadence while nobody is connected (no file work happens).
IDLE_SLEEP_SECONDS = 30.0
# Republish even without changes so a fresh client sees data within this bound.
HEARTBEAT_SECONDS = 600.0
# Rollout tail large enough to contain at least one rate_limits event.
CODEX_TAIL_BYTES = 256 * 1024
# Claude aggregation windows.
CLAUDE_WINDOW_HOURS = 5
# Only touch transcripts that were active recently; older files can't affect
# the today/5h sums and skipping them keeps the scan cheap.
CLAUDE_SCAN_MTIME_HOURS = 26
# Per-file LRU of message ids already counted (dedup across content-block
# lines that repeat the same usage payload).
_DEDUP_IDS_PER_FILE = 128
# Official Claude limit percentages come from the same OAuth endpoint the CLI's
# /usage screen uses — account-wide numbers (all machines), matching the
# console. The token is Claude Code's own OAuth credential (Keychain on macOS,
# ~/.claude/.credentials.json elsewhere); Claude Code keeps it refreshed. This
# is the one network call in this module: one GET per TTL window — at the poll
# cadence that's ~24 requests/hour, far below any rate limit, and every failure
# (expired token, endpoint change, 429) degrades to the local token counters.
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_OAUTH_BETA_HEADER = "oauth-2025-04-20"
CLAUDE_KEYCHAIN_SERVICE = "Claude Code-credentials"
CLAUDE_CREDENTIALS_FILE = Path.home() / ".claude" / ".credentials.json"
CLAUDE_LIMITS_TTL_SECONDS = 60.0
CLAUDE_LIMITS_HTTP_TIMEOUT = 10.0


# ── Codex: official rate-limit snapshot from rollout files ─────────────────


def _newest_rollout(root: Path) -> Path | None:
    """Newest rollout file under the date-sharded sessions dir, cheaply.

    The layout is ``YYYY/MM/DD/rollout-*.jsonl``; walking date dirs in
    descending order finds the newest file without statting the whole tree.
    """
    if not root.is_dir():
        return None
    try:
        years = sorted(
            (p for p in root.iterdir() if p.is_dir() and p.name.isdigit()),
            key=lambda p: p.name,
            reverse=True,
        )
        for year in years:
            months = sorted(
                (p for p in year.iterdir() if p.is_dir()),
                key=lambda p: p.name,
                reverse=True,
            )
            for month in months:
                days = sorted(
                    (p for p in month.iterdir() if p.is_dir()),
                    key=lambda p: p.name,
                    reverse=True,
                )
                for day in days:
                    files = list(day.glob("rollout-*.jsonl"))
                    if files:
                        return max(files, key=lambda f: f.stat().st_mtime)
    except OSError:
        return None
    return None


def _window_payload(win: Any) -> dict[str, Any] | None:
    if not isinstance(win, dict):
        return None
    used = win.get("used_percent")
    if not isinstance(used, (int, float)):
        return None
    return {
        "used_percent": float(used),
        "window_minutes": win.get("window_minutes"),
        "resets_at": win.get("resets_at"),
    }


def read_codex_usage(root: Path | None = None) -> dict[str, Any] | None:
    """Latest official rate-limit percentages from the newest Codex rollout.

    Returns None when Codex isn't installed / has no rollouts.
    """
    root = root if root is not None else config.codex_sessions_path
    newest = _newest_rollout(root)
    if newest is None:
        return None
    try:
        size = newest.stat().st_size
        with open(newest, "rb") as fh:
            if size > CODEX_TAIL_BYTES:
                fh.seek(size - CODEX_TAIL_BYTES)
            tail = fh.read().decode("utf-8", errors="ignore")
        mtime = newest.stat().st_mtime
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if '"rate_limits"' not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else obj
        limits = payload.get("rate_limits")
        if not isinstance(limits, dict):
            continue
        return {
            "primary": _window_payload(limits.get("primary")),
            "secondary": _window_payload(limits.get("secondary")),
            "updated_at": mtime,
        }
    return None


# ── Claude: official limit percentages via the CLI's OAuth credential ──────


def _token_from_creds_json(raw: str) -> str | None:
    """Extract a still-valid access token from Claude Code's credentials JSON."""
    try:
        creds = json.loads(raw)
    except json.JSONDecodeError:
        return None
    oauth = creds.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return None
    expires_at = oauth.get("expiresAt")
    if isinstance(expires_at, (int, float)) and expires_at / 1000 <= time.time():
        return None  # expired — Claude Code will refresh it on its next run
    token = oauth.get("accessToken")
    return token if isinstance(token, str) and token else None


def _claude_oauth_token() -> str | None:
    if sys.platform == "darwin":
        try:
            proc = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    CLAUDE_KEYCHAIN_SERVICE,
                    "-w",
                ],
                capture_output=True,
                text=True,
                timeout=5.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            proc = None
        if proc is not None and proc.returncode == 0:
            token = _token_from_creds_json(proc.stdout.strip())
            if token:
                return token
    try:
        return _token_from_creds_json(CLAUDE_CREDENTIALS_FILE.read_text())
    except OSError:
        return None


def _iso_to_epoch(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _limit_window(win: Any) -> dict[str, Any] | None:
    if not isinstance(win, dict):
        return None
    used = win.get("utilization")
    if not isinstance(used, (int, float)):
        return None
    return {
        "used_percent": float(used),
        "resets_at": _iso_to_epoch(win.get("resets_at")),
    }


def _parse_oauth_usage(data: Any) -> dict[str, Any] | None:
    """Shape the /api/oauth/usage response into {five_hour, seven_day}."""
    if not isinstance(data, dict):
        return None
    five_hour = _limit_window(data.get("five_hour"))
    seven_day = _limit_window(data.get("seven_day"))
    if five_hour is None and seven_day is None:
        return None
    return {"five_hour": five_hour, "seven_day": seven_day}


def read_claude_limits() -> dict[str, Any] | None:
    """Account-wide Claude limit percentages, or None (degrade to tokens)."""
    token = _claude_oauth_token()
    if not token:
        return None
    try:
        resp = httpx.get(
            CLAUDE_USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": CLAUDE_OAUTH_BETA_HEADER,
            },
            timeout=CLAUDE_LIMITS_HTTP_TIMEOUT,
        )
    except Exception:  # noqa: BLE001 - any transport error degrades to tokens
        logger.debug("usage: claude limits fetch failed", exc_info=True)
        return None
    if resp.status_code != 200:
        logger.debug("usage: claude limits endpoint returned %s", resp.status_code)
        return None
    try:
        return _parse_oauth_usage(resp.json())
    except ValueError:
        return None


# ── Claude: token totals aggregated from transcripts ───────────────────────


@dataclass
class _FileCache:
    """Incremental parse state for one transcript file."""

    offset: int = 0
    # epoch-hour -> [input, output, cache_read, cache_creation]
    buckets: dict[int, list[int]] = field(default_factory=dict)
    recent_ids: "OrderedDict[str, None]" = field(default_factory=OrderedDict)


def _zero_totals() -> dict[str, int]:
    return {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}


class UsageCollector:
    """Builds the combined usage snapshot; safe to call from any thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._claude_files: dict[str, _FileCache] = {}
        self._claude_updated_at: float | None = None
        # TTL cache for the official-limits fetch so concurrent REST hits and
        # the publisher loop don't multiply network calls.
        self._claude_limits: dict[str, Any] | None = None
        self._claude_limits_at = 0.0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "codex": self._codex_safe(),
                "claude": self._claude_safe(),
            }

    # -- codex -----------------------------------------------------------

    def _codex_safe(self) -> dict[str, Any] | None:
        try:
            return read_codex_usage()
        except Exception:  # noqa: BLE001
            logger.exception("usage: codex read failed")
            return None

    # -- claude ----------------------------------------------------------

    def _claude_safe(self) -> dict[str, Any] | None:
        try:
            return self._claude()
        except Exception:  # noqa: BLE001
            logger.exception("usage: claude aggregation failed")
            return None

    def _claude(self) -> dict[str, Any] | None:
        root = config.claude_projects_path
        if not root.is_dir():
            return None
        now = time.time()
        cutoff = now - CLAUDE_SCAN_MTIME_HOURS * 3600
        seen_recent = False
        for f in root.glob("*/*.jsonl"):
            try:
                st = f.stat()
            except OSError:
                continue
            key = str(f)
            if st.st_mtime < cutoff:
                self._claude_files.pop(key, None)
                continue
            seen_recent = True
            if self._claude_updated_at is None or st.st_mtime > self._claude_updated_at:
                self._claude_updated_at = st.st_mtime
            self._ingest(f, key, st.st_size)

        if not seen_recent and not self._claude_files:
            # No recent activity — still show a zero row if Claude is set up
            # on this machine at all (any project dir exists).
            try:
                next(root.iterdir())
            except (StopIteration, OSError):
                return None

        midnight = (
            datetime.now()
            .astimezone()
            .replace(hour=0, minute=0, second=0, microsecond=0)
        )
        today_start = midnight.timestamp()
        window_start = now - CLAUDE_WINDOW_HOURS * 3600

        today = _zero_totals()
        last_5h = _zero_totals()
        keys = ("input", "output", "cache_read", "cache_creation")
        for cache in self._claude_files.values():
            stale = [h for h in cache.buckets if (h + 1) * 3600 < cutoff]
            for h in stale:
                del cache.buckets[h]
            for h, vals in cache.buckets.items():
                bucket_end = (h + 1) * 3600
                if bucket_end > today_start:
                    for k, v in zip(keys, vals):
                        today[k] += v
                if bucket_end > window_start:
                    for k, v in zip(keys, vals):
                        last_5h[k] += v

        if now - self._claude_limits_at >= CLAUDE_LIMITS_TTL_SECONDS:
            self._claude_limits = read_claude_limits()
            self._claude_limits_at = now

        return {
            "today": today,
            "last_5h": last_5h,
            "limits": self._claude_limits,
            "updated_at": self._claude_updated_at,
        }

    def _ingest(self, path: Path, key: str, size: int) -> None:
        cache = self._claude_files.get(key)
        if cache is None or size < cache.offset:
            cache = _FileCache()  # new file, or truncated/rotated — reparse
            self._claude_files[key] = cache
        if size == cache.offset:
            return
        try:
            with open(path, "rb") as fh:
                fh.seek(cache.offset)
                data = fh.read(size - cache.offset)
        except OSError:
            return
        lines = data.split(b"\n")
        if data.endswith(b"\n"):
            complete = lines[:-1]
            consumed = len(data)
        else:
            # Trailing partial line: parse next poll once it's complete.
            complete = lines[:-1]
            consumed = len(data) - len(lines[-1])
        cache.offset += consumed
        for raw in complete:
            if b'"usage"' not in raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            msg = obj.get("message")
            if not isinstance(msg, dict):
                continue
            usage = msg.get("usage")
            if not isinstance(usage, dict):
                continue
            mid = msg.get("id")
            if isinstance(mid, str) and mid:
                if mid in cache.recent_ids:
                    continue  # same message, another content-block line
                cache.recent_ids[mid] = None
                while len(cache.recent_ids) > _DEDUP_IDS_PER_FILE:
                    cache.recent_ids.popitem(last=False)
            ts = obj.get("timestamp")
            epoch = _parse_ts(ts)
            if epoch is None:
                continue
            bucket = cache.buckets.setdefault(int(epoch // 3600), [0, 0, 0, 0])
            bucket[0] += int(usage.get("input_tokens") or 0)
            bucket[1] += int(usage.get("output_tokens") or 0)
            bucket[2] += int(usage.get("cache_read_input_tokens") or 0)
            bucket[3] += int(usage.get("cache_creation_input_tokens") or 0)


def _parse_ts(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


# ── Publisher loop ──────────────────────────────────────────────────────────


def _signature(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, sort_keys=True, default=str)


async def usage_publisher_loop(bus: "EventBus", collector: UsageCollector) -> None:
    """Run until cancelled. Emits ``agent_usage`` events on the bus."""
    last_signature: str | None = None
    last_published = 0.0
    while True:
        try:
            if bus.subscriber_count == 0:
                await asyncio.sleep(IDLE_SLEEP_SECONDS)
                continue
            snapshot = await asyncio.to_thread(collector.snapshot)
            sig = _signature(snapshot)
            now = time.monotonic()
            if sig != last_signature or now - last_published >= HEARTBEAT_SECONDS:
                await bus.publish({"type": "agent_usage", **snapshot})
                last_signature = sig
                last_published = now
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("usage publisher iteration failed")
            await asyncio.sleep(30.0)


__all__ = [
    "UsageCollector",
    "read_claude_limits",
    "read_codex_usage",
    "usage_publisher_loop",
]
