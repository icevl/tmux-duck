"""Slack connector (Socket Mode).

Maps each Slack thread to one tmux window running the configured agent
(thread = session). Inbound messages are forwarded into the agent; agent
output is buffered per turn and posted back into the originating thread.
No public URL is required — Socket Mode keeps a persistent WebSocket open,
mirroring how the Telegram transport long-polls.

Config (``config_json``) keys:
  - ``bot_token``       Slack bot token (``xoxb-…``)            [required]
  - ``app_token``       Slack app-level token (``xapp-…``)      [required]
  - ``default_runtime`` agent to launch: ``codex`` | ``claude``
  - ``cwd``             working directory for new sessions      [required]
  - ``instructions``    standing instructions injected per thread
  - ``allowed_channels` optional list of channel ids to accept
  - ``allowed_users``   optional list of user ids to accept

The bot acts only when @-mentioned; ordinary channel messages are ignored.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from ..session_monitor import NewMessage
from ..tmux_manager import tmux_manager
from . import bridge, store
from .base import (
    BaseConnector,
    ConfigField,
    ConnectorContext,
    register_connector_type,
)
from .store import ConnectorRecord

logger = logging.getLogger(__name__)

# Deny if nobody clicks within this window. Kept below the Claude hook's
# 600s ceiling so the endpoint answers before the hook itself times out.
APPROVAL_TIMEOUT_SECONDS = 540
# Pane polling cadence, and how long after the last activity a window is still
# considered "in a turn" and worth polling for prompts. Idle windows aren't
# polled at all — this keeps steady CPU (capture-pane) near zero when nothing
# is happening.
_POLL_INTERVAL = 2.5
_ACTIVE_WINDOW_SECONDS = 30
# Kill a thread's tmux window after this much inactivity, so idle Slack
# threads don't leak agent processes. A thread stays one live session until
# then; the timer is persisted in the DB (survives restarts) and checked on
# a slow cadence.
IDLE_TTL_SECONDS = 24 * 3600  # 1 day
_REAP_INTERVAL_SECONDS = 300
# How often the connector freshens its working tree, and the guard that keeps
# the pull from yanking files out from under a live turn. A pull only runs when
# the tree is clean, no merge/rebase is in progress, the branch tracks an
# upstream, and no thread has been active within this window (ff-only — diverged
# branches are skipped, never merged).
_REPO_REFRESH_INTERVAL_SECONDS = 3600
# Slack mention markup: <@U123> or <@U123|name>
_MENTION_RE = re.compile(r"<@[A-Z0-9]+(?:\|[^>]+)?>")
# Cap per-attachment download size.
_MAX_FILE_BYTES = 25 * 1024 * 1024


def _safe_filename(name: str) -> str:
    cleaned = "".join(c for c in str(name) if c.isalnum() or c in "._- ").strip()
    return (cleaned or "file")[:120]


@register_connector_type("slack")
class SlackConnector(BaseConnector):
    """A single configured Slack workspace integration."""

    type_label = "Slack"

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField("default_runtime", "Agent runtime", "runtime", required=True),
            ConfigField("cwd", "Working directory", "directory", required=True),
            ConfigField(
                "bot_token",
                "Bot token (xoxb-…)",
                "secret",
                required=True,
                placeholder="xoxb-…",
            ),
            ConfigField(
                "app_token",
                "App-level token (xapp-…)",
                "secret",
                required=True,
                placeholder="xapp-…",
            ),
            ConfigField(
                "instructions",
                "Custom instructions",
                "textarea",
                placeholder="Standing instructions injected at the start of "
                "every new thread…",
            ),
            ConfigField(
                "allowed_channels",
                "Allowed channels (comma-separated ids)",
                "list",
                placeholder="C0123, C0456",
            ),
            ConfigField(
                "extra_read_commands",
                "Trusted read-only commands",
                "list",
                placeholder="rtk, kubectl get",
                help="First-word commands to always treat as reads (no "
                "approval). Use for custom read tools the gate can't recognize.",
            ),
            ConfigField(
                "read_only",
                "Read-only (block all writes)",
                "bool",
                help="When on, every mutating operation is denied regardless "
                "of the access list below.",
            ),
            ConfigField(
                "acl",
                "Access control",
                "acl",
                help="Users allowed to use the bot. Tick Write to let a user "
                "perform mutating operations (still confirmed via Approve/Deny). "
                "Empty = anyone may use it, read-only.",
            ),
        ]

    def __init__(self, record: ConnectorRecord, ctx: ConnectorContext) -> None:
        super().__init__(record, ctx)
        self._app: AsyncApp | None = None
        self._handler: AsyncSocketModeHandler | None = None
        self._listener = None
        # window_id → {channel, thread_ts}
        self._outbound: dict[str, dict[str, Any]] = {}
        # window_id → set of transcript coords already posted (dedup)
        self._posted: dict[str, set] = {}
        # req_id → Future resolved by an Approve/Deny button click
        self._pending: dict[str, asyncio.Future[bool]] = {}
        # Background poller: Codex prompt interception + idle-window reaping
        self._codex_task: asyncio.Task | None = None
        # window_id → last handled prompt fingerprint (avoid re-asking)
        self._codex_last: dict[str, str] = {}
        # window_id → monotonic time of last activity (gates pane polling)
        self._active_at: dict[str, float] = {}
        # window_id → Slack user id who drove the latest turn (for write ACL)
        self._last_user: dict[str, str] = {}
        # window_id → monotonic time of the last "write blocked" note (throttle)
        self._block_note_at: dict[str, float] = {}

    # --- config helpers ---------------------------------------------------

    @property
    def _cwd(self) -> str:
        return str(self.config.get("cwd") or "").strip()

    @property
    def _runtime_name(self) -> str:
        return str(self.config.get("default_runtime") or "codex").strip() or "codex"

    @property
    def _instructions(self) -> str:
        return str(self.config.get("instructions") or "")

    def _acl(self) -> list[dict[str, Any]]:
        acl = self.config.get("acl")
        return acl if isinstance(acl, list) else []

    def _acl_users(self) -> set[str]:
        return {str(e["user"]) for e in self._acl() if e.get("user")}

    def _is_allowed(self, channel: str, user: str, is_dm: bool = False) -> bool:
        # The channel allowlist gates public/private channels by id. DM channel
        # ids are per-user and not listable, so for DMs we gate on the user ACL
        # only (a DM is inherently 1:1 with the person who opened it).
        if not is_dm:
            channels = self.config.get("allowed_channels") or []
            if channels and channel not in channels:
                return False
        acl_users = self._acl_users()
        # Empty ACL → anyone may use the bot (read-only, since no write grants).
        if acl_users and user not in acl_users:
            return False
        return True

    def _may_write(self, window_id: str) -> bool:
        """Whether the user driving this window's turn may perform writes."""
        if self.config.get("read_only"):
            return False
        user = self._last_user.get(window_id)
        if not user:
            return False
        for entry in self._acl():
            if entry.get("user") == user:
                return bool(entry.get("write"))
        return False

    # --- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        bot_token = str(self.config.get("bot_token") or "").strip()
        app_token = str(self.config.get("app_token") or "").strip()
        if not bot_token or not app_token:
            raise RuntimeError("slack connector missing bot_token/app_token")
        if not self._cwd:
            raise RuntimeError("slack connector missing cwd")

        self._app = AsyncApp(token=bot_token, logger=logger)
        self._register_handlers(self._app)
        self._handler = AsyncSocketModeHandler(self._app, app_token)

        # connect_async keeps the socket open in background tasks and returns,
        # which fits our start()/stop() model (start_async would block).
        await self._handler.connect_async()

        if self._ctx.monitor is not None:
            self._listener = self._make_listener()
            self._ctx.monitor.add_listener(self._listener)

        # Codex has no PreToolUse hook on this version; intercept its native
        # untrusted-mode approval prompts from the pane instead.
        self._codex_task = asyncio.create_task(
            self._monitor_loop(), name=f"slack-monitor-{self.id}"
        )
        logger.info("Slack connector connected id=%s", self.id)

    async def stop(self) -> None:
        if self._codex_task is not None:
            self._codex_task.cancel()
            try:
                await self._codex_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._codex_task = None
        # Unblock any awaiting approvals so the agents don't hang.
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_result(False)
        self._pending.clear()
        if self._listener is not None and self._ctx.monitor is not None:
            self._ctx.monitor.remove_listener(self._listener)
            self._listener = None
        if self._handler is not None:
            try:
                await self._handler.disconnect_async()
            except Exception:  # noqa: BLE001
                logger.exception("error disconnecting slack handler id=%s", self.id)
            self._handler = None
        self._app = None  # socket handler owns the client lifecycle
        self._outbound.clear()
        self._posted.clear()
        self._codex_last.clear()
        self._active_at.clear()
        self._last_user.clear()
        self._block_note_at.clear()
        logger.info("Slack connector stopped id=%s", self.id)

    # --- inbound (Slack → agent) -----------------------------------------

    def _register_handlers(self, app: AsyncApp) -> None:
        # Socket Mode auto-acks events, so event handlers take no `ack`.
        # Channels are mention-only: a plain channel `message` (which also fires
        # on a mention) is swallowed so the bot doesn't react to ordinary
        # chatter; the mention is handled via `app_mention`. DMs have no mention,
        # so a direct message (`channel_type == "im"`) is handled here directly —
        # one continuous session per DM, no tagging required.
        @app.event("message")
        async def _on_message(event: dict[str, Any]) -> None:
            if event.get("channel_type") != "im":
                return
            try:
                await self._handle_message(event, is_dm=True)
            except Exception:  # noqa: BLE001
                logger.exception("slack DM handling failed id=%s", self.id)

        @app.event("app_mention")
        async def _on_mention(event: dict[str, Any]) -> None:
            # A mention inside a DM also arrives as `message.im` (handled above);
            # skip it here so we don't double-handle.
            if (event.get("channel") or "").startswith("D"):
                return
            try:
                await self._handle_message(event, is_dm=False)
            except Exception:  # noqa: BLE001
                logger.exception("slack mention handling failed id=%s", self.id)

        @app.action("connector_approve")
        async def _approve(ack, body: dict[str, Any]) -> None:  # noqa: ANN001
            await ack()
            self._resolve_pending(body, True)

        @app.action("connector_deny")
        async def _deny(ack, body: dict[str, Any]) -> None:  # noqa: ANN001
            await ack()
            self._resolve_pending(body, False)

        @app.action(re.compile(r"^connector_choose:\d+$"))
        async def _choose(ack, body: dict[str, Any]) -> None:  # noqa: ANN001
            await ack()
            try:
                await self._handle_choice(body)
            except Exception:  # noqa: BLE001
                logger.exception("slack choice handling failed id=%s", self.id)

    def _resolve_pending(self, body: dict[str, Any], approved: bool) -> None:
        try:
            req_id = body["actions"][0]["value"]
        except (KeyError, IndexError, TypeError):
            return
        fut = self._pending.get(req_id)
        if fut is not None and not fut.done():
            fut.set_result(approved)

    async def _handle_message(self, event: dict[str, Any], is_dm: bool = False) -> None:
        # Ignore the bot's own messages and edits/deletes (but keep file uploads,
        # which arrive with subtype "file_share").
        if event.get("bot_id"):
            return
        subtype = event.get("subtype")
        if subtype and subtype != "file_share":
            return
        # Strip the leading "<@U…>" mention token(s) so the agent gets a clean
        # instruction rather than the raw Slack mention markup.
        text = _MENTION_RE.sub("", event.get("text") or "").strip()
        channel = event.get("channel") or ""
        user = event.get("user") or ""
        files = event.get("files") or []
        if not channel or (not text and not files):
            return
        if not self._is_allowed(channel, user, is_dm=is_dm):
            logger.info("slack message rejected channel=%s user=%s", channel, user)
            return

        # Session scoping + where replies land.
        #  - DM: one continuous session per DM channel; reply at top level so it
        #    reads as a normal conversation. No mention needed.
        #  - Channel: thread = session; reply inside the thread.
        if is_dm:
            session_key = channel
            reply_thread_ts: str | None = None
            window_name = f"slack-dm-{channel}"
        else:
            thread_root = event.get("thread_ts") or event.get("ts")
            session_key = f"{channel}:{thread_root}"
            reply_thread_ts = thread_root
            window_name = f"slack-{thread_root}"

        # `/new` (DM only): drop the current DM session so the next turn starts
        # with a clean context. Any text after `/new` becomes the first message
        # of the fresh session.
        if is_dm and (text == "/new" or text.startswith(("/new ", "/new\n"))):
            await self._reset_session(session_key)
            text = text[len("/new") :].strip()
            if not text and not files:
                if self._app is not None:
                    await self._app.client.chat_postMessage(
                        channel=channel,
                        text="🆕 Fresh session — send your next message.",
                    )
                return

        # Acknowledge receipt with a 👀 reaction before the (slow) work starts.
        msg_ts = event.get("ts")
        if msg_ts and self._app is not None:
            try:
                await self._app.client.reactions_add(
                    channel=channel, timestamp=msg_ts, name="eyes"
                )
            except Exception:  # noqa: BLE001
                # Non-fatal: usually missing reactions:write scope or a dup.
                logger.debug("could not add 👀 reaction id=%s", self.id)

        # Download any attachments and reference their local paths in the
        # prompt (same `(image attached: …)` convention as Telegram/web), so
        # the agent can read them.
        if files:
            refs, failed = await self._download_files(files)
            if refs:
                joined = "\n".join(refs)
                text = f"{text}\n{joined}".strip() if text else joined
            if failed and self._app is not None:
                await self._app.client.chat_postMessage(
                    channel=channel,
                    thread_ts=reply_thread_ts,
                    text=(
                        f"⚠️ Couldn't fetch {failed} attachment(s) — check the "
                        f"bot's `files:read` scope."
                    ),
                )
            if not text:
                return

        try:
            window_id, created = await bridge.ensure_window(
                connector_id=self.id,
                external_id=session_key,
                runtime_name=self._runtime_name,
                cwd=self._cwd,
                window_name=window_name,
                instructions=self._instructions,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("failed to start session id=%s", self.id)
            if self._app is not None:
                await self._app.client.chat_postMessage(
                    channel=channel,
                    thread_ts=reply_thread_ts,
                    text=f"⚠️ Couldn't start a session: {exc}",
                )
            return

        # Route this window's output back to where the message came from. Keyed
        # by window id (stable immediately) rather than session id (discovered
        # asynchronously, especially for the Codex runtime).
        self._outbound[window_id] = {
            "channel": channel,
            "thread_ts": reply_thread_ts,
        }
        self._last_user[window_id] = user
        self._active_at[window_id] = time.monotonic()
        store.touch_session_mapping_by_window(window_id)

        # Codex has no system-prompt flag, so on a fresh window we prepend the
        # connector instructions (+ baked guidance) to its first message
        # (Claude already got them as a launch system prompt).
        send_text = text
        if created and self._runtime_name == "codex":
            preamble = bridge.combined_instructions(self._instructions)
            send_text = f"{preamble}\n\n{text}".strip() if text else preamble
        ok = await bridge.send_user_message(window_id, send_text)
        if not ok and self._app is not None:
            await self._app.client.chat_postMessage(
                channel=channel,
                thread_ts=reply_thread_ts,
                text="⚠️ Failed to deliver the message to the agent.",
            )

    async def _download_files(
        self, files: list[dict[str, Any]]
    ) -> tuple[list[str], int]:
        """Save Slack attachments locally; return (prompt-refs, failed count).

        Needs the bot's ``files:read`` scope. Images are referenced as
        ``(image attached: <path>)``, others as ``(file attached: <path>)`` —
        the convention the agent already understands.
        """
        from .approval import connectors_state_dir

        uploads = connectors_state_dir() / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        bot_token = str(self.config.get("bot_token") or "")
        refs: list[str] = []
        failed = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            for f in files:
                url = f.get("url_private_download") or f.get("url_private")
                size = f.get("size")
                if not url or (isinstance(size, int) and size > _MAX_FILE_BYTES):
                    failed += 1
                    continue
                try:
                    resp = await client.get(
                        url, headers={"Authorization": f"Bearer {bot_token}"}
                    )
                    resp.raise_for_status()
                except Exception:  # noqa: BLE001
                    logger.exception("slack file download failed id=%s", self.id)
                    failed += 1
                    continue
                # Without files:read Slack serves an HTML login page with 200.
                if "text/html" in resp.headers.get("content-type", ""):
                    failed += 1
                    continue
                name = _safe_filename(f.get("name") or f.get("id") or "file")
                dest = uploads / f"{f.get('id', 'file')}_{name}"
                try:
                    dest.write_bytes(resp.content)
                except OSError:
                    failed += 1
                    continue
                mimetype = str(f.get("mimetype") or "")
                kind = "image" if mimetype.startswith("image/") else "file"
                refs.append(f"({kind} attached: {dest})")
        return refs, failed

    # --- outbound (agent → Slack) ----------------------------------------

    def _make_listener(self):
        async def _listener(msg: NewMessage) -> None:
            try:
                await self._on_agent_message(msg)
            except Exception:  # noqa: BLE001
                logger.exception("slack outbound failed id=%s", self.id)

        return _listener

    async def _on_agent_message(self, msg: NewMessage) -> None:
        window_id = bridge.window_for_session(msg.session_id)
        if not window_id:
            return
        target = self._outbound.get(window_id)
        if target is None:
            # This session isn't owned by this connector's threads.
            return
        if msg.message_type == "completion":
            # Turn finished → no prompt is coming; stop polling immediately.
            store.touch_session_mapping_by_window(window_id)
            self._active_at.pop(window_id, None)
            return
        # Agent output → the turn is live; keep polling for a short tail so a
        # prompt that appears right after its last output is still caught.
        self._active_at[window_id] = time.monotonic()
        if not msg.is_complete:
            return  # skip streaming/partial chunks; post only finalized blocks
        piece = format_agent_part(msg)
        if not piece or self._app is None:
            return
        # Dedup: the monitor may re-emit a message as it streams to completion.
        key = (msg.transcript_offset, msg.transcript_index)
        seen = self._posted.setdefault(window_id, set())
        if key in seen:
            return
        seen.add(key)
        store.touch_session_mapping_by_window(window_id)
        blocks = build_message_blocks(piece)
        if blocks:
            # Markdown tables → real Block Kit table blocks. `text` is the
            # notification fallback (required when sending blocks).
            await self._app.client.chat_postMessage(
                channel=target["channel"],
                thread_ts=target["thread_ts"],
                text=piece[:300],
                blocks=blocks,
            )
        else:
            await self._app.client.chat_postMessage(
                channel=target["channel"],
                thread_ts=target["thread_ts"],
                text=to_slack_mrkdwn(piece)[:38000],
                mrkdwn=True,
            )

    # --- write-gate approval ---------------------------------------------

    def _resolve_thread(self, window_id: str) -> tuple[str, str] | None:
        """Return ``(channel, thread_ts)`` for a window, or None if unknown."""
        target = self._outbound.get(window_id)
        if target is not None:
            return target["channel"], target["thread_ts"]
        mapping = store.find_mapping_by_window(window_id)
        if mapping is None:
            return None
        channel, _, thread_ts = mapping.external_id.partition(":")
        if not channel or not thread_ts:
            return None
        return channel, thread_ts

    async def request_write_approval(
        self, window_id: str, title: str, detail: str
    ) -> bool:
        if self._app is None:
            return True
        thread = self._resolve_thread(window_id)
        if thread is None:
            # Can't route an approval request → fail open rather than hang.
            logger.warning("no slack thread for window=%s; allowing", window_id)
            return True
        channel, thread_ts = thread

        # ACL: hard-deny the write before even asking when read-only mode is on
        # or the driving user lacks the Write grant.
        if not self._may_write(window_id):
            await self._note_write_blocked(channel, thread_ts, window_id)
            return False

        req_id = secrets.token_hex(8)
        fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut

        snippet = detail.strip()
        if len(snippet) > 2800:
            snippet = snippet[:2800] + "…"
        blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"🔐 *{title}*\n```{snippet}```"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "style": "primary",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "action_id": "connector_approve",
                        "value": req_id,
                    },
                    {
                        "type": "button",
                        "style": "danger",
                        "text": {"type": "plain_text", "text": "Deny"},
                        "action_id": "connector_deny",
                        "value": req_id,
                    },
                ],
            },
        ]
        posted = None
        try:
            posted = await self._app.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"🔐 {title}",
                blocks=blocks,
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to post approval card id=%s", self.id)
            self._pending.pop(req_id, None)
            return True  # fail open

        try:
            approved = await asyncio.wait_for(fut, timeout=APPROVAL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            approved = False
        finally:
            self._pending.pop(req_id, None)

        # Replace the buttons with the outcome so it can't be clicked twice.
        if posted is not None:
            verdict = "✅ Approved" if approved else "🚫 Denied"
            try:
                await self._app.client.chat_update(
                    channel=channel,
                    ts=str(posted["ts"]),
                    text=f"{verdict}: {title}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"{verdict} — *{title}*\n```{snippet}```",
                            },
                        }
                    ],
                )
            except Exception:  # noqa: BLE001
                pass
        return approved

    async def _note_write_blocked(
        self, channel: str, thread_ts: str, window_id: str
    ) -> None:
        """Tell the thread a write was blocked, throttled to once per 30s."""
        now = time.monotonic()
        if now - self._block_note_at.get(window_id, 0.0) < 30.0:
            return
        self._block_note_at[window_id] = now
        reason = (
            "read-only mode is on"
            if self.config.get("read_only")
            else "you don't have Write access"
        )
        if self._app is None:
            return
        try:
            await self._app.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"🚫 Write blocked — {reason}.",
            )
        except Exception:  # noqa: BLE001
            pass

    # --- background monitor: codex prompts + idle reaping ----------------

    async def _monitor_loop(self) -> None:
        from ..terminal_parser import extract_interactive_content, parse_options

        last_reap = time.monotonic()
        # First freshen only after a full interval, so a just-deployed checkout
        # isn't pulled the instant the connector boots.
        last_repo_refresh = time.monotonic()
        while True:
            try:
                await asyncio.sleep(_POLL_INTERVAL)
                now = time.monotonic()
                mappings = store.list_session_mappings(self.id)
                for mapping in mappings:
                    # Only poll windows with recent activity (a turn in flight);
                    # idle windows produce no prompts, so skip their capture.
                    active = now - self._active_at.get(mapping.window_id, 0.0)
                    if active > _ACTIVE_WINDOW_SECONDS:
                        continue
                    await self._check_window(
                        mapping.window_id,
                        mapping.runtime,
                        extract_interactive_content,
                        parse_options,
                    )
                if now - last_reap >= _REAP_INTERVAL_SECONDS:
                    last_reap = now
                    await self._reap_idle(mappings)
                if now - last_repo_refresh >= _REPO_REFRESH_INTERVAL_SECONDS:
                    last_repo_refresh = now
                    await self._maybe_refresh_repo()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("monitor loop error id=%s", self.id)

    def _forget_window(self, window_id: str) -> None:
        self._outbound.pop(window_id, None)
        self._posted.pop(window_id, None)
        self._codex_last.pop(window_id, None)
        self._active_at.pop(window_id, None)
        self._last_user.pop(window_id, None)
        self._block_note_at.pop(window_id, None)

    async def _reset_session(self, external_id: str) -> None:
        """Tear down the agent session bound to ``external_id`` (used by `/new`).

        Kills the tmux window, drops the persisted mapping, and clears in-memory
        state so the next message spins up a fresh agent with a clean context.
        """
        mapping = store.get_session_mapping(self.id, external_id)
        if mapping is None:
            return
        try:
            await tmux_manager.kill_window(mapping.window_id)
        except Exception:  # noqa: BLE001
            logger.debug("reset: kill_window failed id=%s", self.id)
        store.delete_session_mapping(self.id, external_id)
        self._forget_window(mapping.window_id)

    async def _reap_idle(self, mappings) -> None:  # noqa: ANN001
        """Kill tmux windows for threads idle past the TTL; drop dead mappings.

        Idle age comes from the DB's ``last_activity_at`` (wall-clock), so the
        timer survives process restarts.
        """
        for mapping in mappings:
            window_id = mapping.window_id
            window = await tmux_manager.find_window_by_id(window_id)
            if window is None:
                # Window already gone — clean up the stale mapping/state.
                store.delete_session_mapping(self.id, mapping.external_id)
                self._forget_window(window_id)
                continue
            idle = _idle_seconds(mapping.last_activity_at)
            if idle is None:
                # No timestamp yet (legacy row) — stamp it and grant a cycle.
                store.touch_session_mapping_by_window(window_id)
                continue
            if idle < IDLE_TTL_SECONDS:
                continue
            thread = self._resolve_thread(window_id)
            await tmux_manager.kill_window(window_id)
            store.delete_session_mapping(self.id, mapping.external_id)
            self._forget_window(window_id)
            if thread is not None and self._app is not None:
                channel, thread_ts = thread
                try:
                    await self._app.client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts,
                        text="💤 Session closed after inactivity. Mention me to start a new one.",
                    )
                except Exception:  # noqa: BLE001
                    pass

    def _has_active_turn(self) -> bool:
        """True if any thread has had a turn in flight within the active window."""
        now = time.monotonic()
        return any(
            now - ts <= _ACTIVE_WINDOW_SECONDS for ts in self._active_at.values()
        )

    async def _maybe_refresh_repo(self) -> None:
        """Fast-forward the connector's working tree when it's safe and idle.

        Bails out unless every guard holds: cwd is a git work tree, the tree is
        clean (a dirty tree or unresolved conflict shows up in ``--porcelain``),
        no merge is in progress, and the branch tracks an upstream. ``--ff-only``
        means a diverged branch is left untouched rather than merged. Skipped
        entirely while any thread is mid-turn so files never move under an agent.
        """
        cwd = self._cwd
        if not cwd or self._has_active_turn():
            return
        rc, _ = await self._run_git(cwd, "rev-parse", "--is-inside-work-tree")
        if rc != 0:
            return
        rc, out = await self._run_git(cwd, "status", "--porcelain")
        if rc != 0 or out.strip():
            return
        rc, _ = await self._run_git(
            cwd, "rev-parse", "--verify", "--quiet", "MERGE_HEAD"
        )
        if rc == 0:
            return
        rc, _ = await self._run_git(
            cwd, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"
        )
        if rc != 0:
            return
        rc, out = await self._run_git(cwd, "pull", "--ff-only")
        msg = out.strip().splitlines()[-1] if out.strip() else ""
        if rc == 0:
            logger.info(
                "connector repo freshened id=%s cwd=%s: %s",
                self.id,
                cwd,
                msg or "up to date",
            )
        else:
            logger.info(
                "connector repo pull skipped (not fast-forward) id=%s cwd=%s: %s",
                self.id,
                cwd,
                msg,
            )

    @staticmethod
    async def _run_git(cwd: str, *args: str) -> tuple[int, str]:
        """Run ``git -C cwd <args>``; return (returncode, combined output)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                cwd,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            return proc.returncode or 0, out.decode("utf-8", "replace")
        except (OSError, asyncio.TimeoutError):
            return 1, ""

    async def _check_window(
        self, window_id: str, runtime: str, extract_interactive_content, parse_options
    ) -> None:  # noqa: ANN001
        window = await tmux_manager.find_window_by_id(window_id)
        if window is None:
            self._codex_last.pop(window_id, None)
            return
        pane = await tmux_manager.capture_pane(window_id)
        if not pane:
            return
        # Startup prompts (folder-trust, bypass-permissions) are auto-confirmed
        # by the Claude runtime — never forward them to Slack as choices.
        if runtime == "claude":
            from ..runtimes.claude import _classify_startup_prompt

            if _classify_startup_prompt(pane) is not None:
                return
        content = extract_interactive_content(pane, runtime=runtime)
        if content is None:
            self._codex_last.pop(window_id, None)
            return
        parsed = parse_options(content.content)
        if parsed is None or not parsed.options:
            return
        labels = [o.label for o in parsed.options]

        fingerprint = f"{content.name}:{len(labels)}:{content.content[:80]}"
        if self._codex_last.get(window_id) == fingerprint:
            return
        self._codex_last[window_id] = fingerprint

        approve_idx, deny_idx = _pick_yes_no(labels)
        # Codex write-approval prompts are a yes/no pair → route through the
        # ACL'd write-gate. Everything else (AskUserQuestion, plan choices, …)
        # is a real question → forward the options to Slack as buttons.
        is_approval = (
            runtime == "codex"
            and approve_idx is not None
            and deny_idx is not None
            and len(labels) <= 3
        )
        if is_approval:
            approved = await self.request_write_approval(
                window_id, "Codex requests approval", content.content
            )
            target_idx = approve_idx if approved else deny_idx
            if target_idx is not None:
                from ..web.interactive_monitor import navigate_and_choose

                await navigate_and_choose(window_id, target_idx, len(labels))
            return

        await self._forward_choice(window_id, content.content, labels)

    async def _forward_choice(
        self, window_id: str, question: str, labels: list[str]
    ) -> None:
        """Surface an agent multiple-choice prompt to Slack as option buttons."""
        thread = self._resolve_thread(window_id)
        if thread is None or self._app is None:
            return
        channel, thread_ts = thread
        total = len(labels)
        elements = [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": (lbl.strip() or f"Option {i + 1}")[:75],
                },
                "action_id": f"connector_choose:{i}",
                "value": f"{window_id}|{i}|{total}",
            }
            for i, lbl in enumerate(labels[:24])
        ]
        prompt = to_slack_mrkdwn(_strip_sentinels(question)).strip()[:2800]
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"❓ {prompt}"}},
            {"type": "actions", "elements": elements},
        ]
        try:
            await self._app.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="❓ The agent needs your input",
                blocks=blocks,
            )
        except Exception:  # noqa: BLE001
            logger.exception("failed to post choice prompt id=%s", self.id)

    async def _handle_choice(self, body: dict[str, Any]) -> None:
        action = (body.get("actions") or [{}])[0]
        try:
            window_id, idx_s, total_s = str(action.get("value", "")).split("|")
            idx, total = int(idx_s), int(total_s)
        except (ValueError, AttributeError):
            return
        from ..web.interactive_monitor import navigate_and_choose

        await navigate_and_choose(window_id, idx, total)
        if self._app is None:
            return
        # Replace the buttons with the chosen option so it can't be re-clicked.
        chosen = (action.get("text") or {}).get("text", "selected")
        try:
            await self._app.client.chat_update(
                channel=body["channel"]["id"],
                ts=body["message"]["ts"],
                text=f"✅ {chosen}",
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"✅ Chose: *{chosen}*"},
                    }
                ],
            )
        except Exception:  # noqa: BLE001
            pass


_EXPQUOTE_MARKERS = ("\x02EXPQUOTE_START\x02", "\x02EXPQUOTE_END\x02")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")


def _strip_sentinels(text: str) -> str:
    for marker in _EXPQUOTE_MARKERS:
        text = text.replace(marker, "")
    return text


def to_slack_mrkdwn(text: str) -> str:
    """Convert GitHub-flavored markdown to Slack mrkdwn.

    `**bold**`/`__bold__` → `*bold*`, `# headings` → bold lines, `- ` bullets
    → `• `, `[t](u)` → `<u|t>`, `~~s~~` → `~s~`. Content inside ``` fences is
    left untouched. Not a full parser — covers what agents actually emit.
    """
    text = _strip_sentinels(text)
    out: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        header = _HEADER_RE.match(line)
        if header:
            line = f"*{header.group(1).strip()}*"
        else:
            line = re.sub(r"^(\s*)[-*]\s+", r"\1• ", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)
        line = re.sub(r"__(.+?)__", r"*\1*", line)
        line = re.sub(r"~~(.+?)~~", r"~\1~", line)
        line = _MD_LINK_RE.sub(r"<\2|\1>", line)
        out.append(line)
    return "\n".join(out)


_TOOL_MARKER_RE = re.compile(r"^\*\*[\w.\-]+\*\*\(")


def format_agent_part(msg: NewMessage) -> str | None:
    """Return the agent's own text answer (raw, sentinel-stripped), or None.

    Posts ONLY the agent's prose. Thinking, tool invocations (``**Bash**(…)``)
    and tool/command output are dropped. The returned text is rendered into
    Slack blocks/mrkdwn by the caller (so markdown tables become real tables).
    """
    text = _strip_sentinels(msg.text or "").strip()
    if not text:
        return None
    if msg.content_type != "text" or msg.role != "assistant":
        return None  # thinking / tool_use / tool_result / local_command
    if _TOOL_MARKER_RE.match(text):
        return None  # stray tool-call marker that arrived as text
    return text


# --- markdown tables → Block Kit table blocks ------------------------------

_TABLE_SEP_CELL_RE = re.compile(r"^:?-{1,}:?$")


def _table_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _is_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    if len(cells) < 2:
        return False
    return all(c and _TABLE_SEP_CELL_RE.match(c) for c in cells)


def _segment_message(text: str) -> list[tuple]:
    """Split text into ('text', str) and ('table', header, rows) segments.

    A GFM pipe table (header row + `---` separator + data rows) becomes a
    table segment; everything else is text. Content inside ``` fences is
    never treated as a table.
    """
    lines = text.split("\n")
    segments: list[tuple] = []
    buf: list[str] = []
    in_fence = False
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            buf.append(line)
            i += 1
            continue
        is_table = (
            not in_fence
            and "|" in line
            and i + 1 < n
            and _is_table_separator(lines[i + 1])
            and len(_table_cells(line)) >= 2
        )
        if is_table:
            if buf:
                segments.append(("text", "\n".join(buf)))
                buf = []
            header = _table_cells(line)
            i += 2  # header + separator
            rows: list[list[str]] = []
            while i < n and "|" in lines[i] and not _is_table_separator(lines[i]):
                if lines[i].lstrip().startswith("```"):
                    break
                rows.append(_table_cells(lines[i]))
                i += 1
            segments.append(("table", header, rows))
        else:
            buf.append(line)
            i += 1
    if buf:
        segments.append(("text", "\n".join(buf)))
    return segments


def _table_cell_text(value: str) -> str:
    # raw_text is literal; drop markdown emphasis/code markers for cleanliness.
    value = re.sub(r"\*\*(.+?)\*\*", r"\1", value)
    value = value.replace("`", "")
    return value[:1000]


def _table_block(header: list[str], rows: list[list[str]]) -> dict[str, Any]:
    ncols = min(max(len(header), 1), 20)

    def mk(cells: list[str]) -> list[dict[str, Any]]:
        padded = (cells + [""] * ncols)[:ncols]
        return [{"type": "raw_text", "text": _table_cell_text(c)} for c in padded]

    out_rows = [mk(header)] + [mk(r) for r in rows[:99]]
    return {"type": "table", "rows": out_rows}


def _chunks(text: str, size: int = 2900) -> list[str]:
    if len(text) <= size:
        return [text]
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > size and cur:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def build_message_blocks(text: str) -> list[dict[str, Any]] | None:
    """Build Block Kit blocks if the text has a table, else None (plain text)."""
    segments = _segment_message(text)
    if not any(s[0] == "table" for s in segments):
        return None
    blocks: list[dict[str, Any]] = []
    for seg in segments:
        if len(blocks) >= 48:
            break
        if seg[0] == "text":
            rendered = to_slack_mrkdwn(seg[1]).strip()
            if not rendered:
                continue
            for chunk in _chunks(rendered):
                blocks.append(
                    {"type": "section", "text": {"type": "mrkdwn", "text": chunk}}
                )
        else:
            blocks.append(_table_block(seg[1], seg[2]))
    return blocks or None


def _idle_seconds(last_activity_at: str | None) -> float | None:
    """Seconds since ``last_activity_at`` (ISO-8601), or None if unparseable."""
    if not last_activity_at:
        return None
    try:
        dt = datetime.fromisoformat(last_activity_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds()


def _pick_yes_no(labels: list[str]) -> tuple[int | None, int | None]:
    """Map option labels to (approve_index, deny_index)."""
    approve_idx: int | None = None
    deny_idx: int | None = None
    for i, label in enumerate(labels):
        low = label.lower()
        if approve_idx is None and any(
            w in low for w in ("yes", "proceed", "approve", "allow", "run")
        ):
            approve_idx = i
        if deny_idx is None and any(
            w in low for w in ("no", "deny", "reject", "cancel", "keep", "don't")
        ):
            deny_idx = i
    return approve_idx, deny_idx


__all__ = ["SlackConnector"]
