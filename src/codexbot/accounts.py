"""Login status and remote-friendly sign-in for agent account profiles.

Status comes from the agents' own CLIs (``claude auth status`` prints JSON;
``codex login status`` exits non-zero when signed out), refreshed on demand
and every few minutes, so a session that silently lost its login shows up in
the UI with a "Sign in" action.

Sign-in runs the CLI's browserless flow under a pty (the Claude CLI only
reads the pasted code from a terminal) with ``BROWSER`` stubbed out so
nothing pops up on the host:

* Claude: ``claude auth login`` prints an authorize URL and waits for the code
  that ``platform.claude.com`` shows after sign-in; the code is written back
  to the pty. A wrong code prints "Invalid code" and keeps waiting.
* Codex: ``codex login --device-auth`` prints a URL plus a one-time code to
  enter there, then polls until the browser side completes.

The URL is published to the web UI, so signing in works from any device.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import config
from .profiles import Profile, profile_store

if TYPE_CHECKING:
    from .web.events import EventBus

logger = logging.getLogger(__name__)

STATUS_REFRESH_SECONDS = 300.0
LOGIN_TIMEOUT_SECONDS = 15 * 60
_STATUS_TIMEOUT_SECONDS = 20.0
_EXTRA_BIN_DIRS = (
    Path.home() / ".local" / "bin",
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/Applications/Codex.app/Contents/Resources"),
)
_RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_RE_CLAUDE_AUTH_URL = re.compile(r"https://\S*/oauth/authorize\?[^\s\x07\x1b]+")
_RE_CODEX_DEVICE_URL = re.compile(r"https://auth\.openai\.com/\S*device\S*")
_RE_CODEX_USER_CODE = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4,6}\b")
_RE_INVALID_CODE = re.compile(r"invalid code[^\n]*", re.IGNORECASE)


def profile_key(profile: Profile) -> str:
    return f"{profile.runtime}:{profile.id or 'default'}"


def _agent_binary(runtime: str) -> str | None:
    command = config.claude_command if runtime == "claude" else config.codex_command
    try:
        name = shlex.split(command)[0]
    except (ValueError, IndexError):
        name = runtime
    if os.path.isabs(name):
        return name if os.access(name, os.X_OK) else None
    search = os.pathsep.join(
        [os.environ.get("PATH", ""), *(str(d) for d in _EXTRA_BIN_DIRS)]
    )
    return shutil.which(name, path=search)


def _agent_env(profile: Profile) -> dict[str, str]:
    env = {**os.environ, **profile.env(), "BROWSER": "/usr/bin/true"}
    env.pop("CLAUDECODE", None)  # codexbot may itself run under Claude Code
    return env


@dataclass
class AccountStatus:
    logged_in: bool | None = None  # None → unknown (CLI missing / failed)
    email: str | None = None
    detail: str | None = None  # plan / auth method, human-readable
    checked_at: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        return {
            "logged_in": self.logged_in,
            "email": self.email,
            "detail": self.detail,
            "checked_at": self.checked_at or None,
        }


def parse_claude_status(output: str) -> AccountStatus:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return AccountStatus(logged_in=None, detail="unreadable auth status")
    if not isinstance(data, dict):
        return AccountStatus(logged_in=None, detail="unreadable auth status")
    detail = data.get("subscriptionType") or data.get("authMethod")
    return AccountStatus(
        logged_in=bool(data.get("loggedIn")),
        email=data.get("email") if isinstance(data.get("email"), str) else None,
        detail=str(detail) if detail and detail != "none" else None,
    )


def parse_codex_status(output: str, returncode: int) -> AccountStatus:
    text = _RE_ANSI.sub("", output).strip()
    line = text.splitlines()[-1].strip() if text else ""
    logged_in = returncode == 0 and "not logged in" not in text.lower()
    return AccountStatus(logged_in=logged_in, detail=line or None)


async def read_status(profile: Profile) -> AccountStatus:
    binary = _agent_binary(profile.runtime)
    if binary is None:
        return AccountStatus(
            logged_in=None,
            detail=f"{profile.runtime} CLI not found",
            checked_at=time.time(),
        )
    args = (
        [binary, "auth", "status"]
        if profile.runtime == "claude"
        else [
            binary,
            "login",
            "status",
        ]
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=_agent_env(profile),
        )
        out, _ = await asyncio.wait_for(proc.communicate(), _STATUS_TIMEOUT_SECONDS)
    except (OSError, asyncio.TimeoutError) as e:
        logger.debug("auth status failed for %s: %s", profile_key(profile), e)
        return AccountStatus(
            logged_in=None, detail="status check failed", checked_at=time.time()
        )
    text = out.decode("utf-8", errors="replace")
    status = (
        parse_claude_status(text)
        if profile.runtime == "claude"
        else parse_codex_status(text, proc.returncode or 0)
    )
    status.checked_at = time.time()
    return status


@dataclass
class LoginFlow:
    profile: Profile
    state: str = (
        "starting"  # starting|awaiting_code|awaiting_browser|succeeded|failed|cancelled
    )
    url: str | None = None
    user_code: str | None = None  # Codex device code to type on the page
    message: str | None = None
    started_at: float = field(default_factory=time.time)
    output: str = ""
    process: asyncio.subprocess.Process | None = None
    master_fd: int | None = None

    @property
    def active(self) -> bool:
        return self.state in ("starting", "awaiting_code", "awaiting_browser")

    def to_payload(self) -> dict[str, Any]:
        return {
            "profile_key": profile_key(self.profile),
            "state": self.state,
            "url": self.url,
            "user_code": self.user_code,
            "message": self.message,
            "started_at": self.started_at,
        }

    def absorb(self, chunk: str) -> bool:
        """Fold new CLI output in; return True when the visible state changed."""
        self.output += chunk
        text = _RE_ANSI.sub("", self.output)
        before = (self.state, self.url, self.user_code, self.message)
        if self.profile.runtime == "claude":
            match = _RE_CLAUDE_AUTH_URL.search(text)
            if match and self.url is None:
                self.url = match.group(0)
                self.state = "awaiting_code"
            invalid = _RE_INVALID_CODE.findall(text)
            if invalid and self.url is not None:
                self.message = invalid[-1].strip()
        else:
            url = _RE_CODEX_DEVICE_URL.search(text)
            code = _RE_CODEX_USER_CODE.search(text)
            if url and code:
                self.url, self.user_code = url.group(0), code.group(0)
                self.state = "awaiting_browser"
        return before != (self.state, self.url, self.user_code, self.message)


class AccountManager:
    """Tracks login status per profile and runs sign-in flows."""

    def __init__(self) -> None:
        self._bus: EventBus | None = None
        self._statuses: dict[str, AccountStatus] = {}
        self._logins: dict[str, LoginFlow] = {}
        self._task: asyncio.Task[None] | None = None
        self._refresh_lock = asyncio.Lock()

    # -- lifecycle -----------------------------------------------------

    async def start(self, bus: "EventBus") -> None:
        self._bus = bus
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._poll_loop(), name="account-status")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        for flow in list(self._logins.values()):
            self._terminate(flow)
        self._bus = None

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self.refresh_all()
            except Exception:
                logger.exception("account status refresh failed")
            await asyncio.sleep(STATUS_REFRESH_SECONDS)

    # -- status --------------------------------------------------------

    def status(self, profile: Profile) -> AccountStatus:
        return self._statuses.get(profile_key(profile), AccountStatus())

    def login(self, profile: Profile) -> LoginFlow | None:
        return self._logins.get(profile_key(profile))

    async def refresh(self, profile: Profile) -> AccountStatus:
        status = await read_status(profile)
        key = profile_key(profile)
        previous = self._statuses.get(key)
        self._statuses[key] = status
        if previous is None or (previous.logged_in, previous.email) != (
            status.logged_in,
            status.email,
        ):
            if (
                previous is not None
                and previous.logged_in
                and status.logged_in is False
            ):
                logger.warning("Profile %s is no longer signed in", key)
            await self._publish({"type": "accounts_changed"})
        return status

    async def refresh_all(self) -> None:
        async with self._refresh_lock:
            for profile in profile_store.list():
                if _agent_binary(profile.runtime) is None and profile.is_default:
                    continue  # runtime not installed at all
                await self.refresh(profile)

    def forget(self, profile: Profile) -> None:
        key = profile_key(profile)
        self._statuses.pop(key, None)
        flow = self._logins.pop(key, None)
        if flow is not None:
            self._terminate(flow)

    # -- sign-in -------------------------------------------------------

    async def start_login(self, profile: Profile) -> LoginFlow:
        key = profile_key(profile)
        existing = self._logins.get(key)
        if existing is not None and existing.active:
            return existing
        binary = _agent_binary(profile.runtime)
        if binary is None:
            raise RuntimeError(f"{profile.runtime} CLI not found")
        args = (
            [binary, "auth", "login"]
            if profile.runtime == "claude"
            else [binary, "login", "--device-auth"]
        )
        master_fd, slave_fd = os.openpty()
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env={**_agent_env(profile), "TERM": "dumb"},
                start_new_session=True,
            )
        except OSError:
            os.close(master_fd)
            raise
        finally:
            os.close(slave_fd)
        flow = LoginFlow(profile=profile, process=process, master_fd=master_fd)
        self._logins[key] = flow
        asyncio.get_running_loop().add_reader(master_fd, self._on_output, flow)
        asyncio.create_task(self._supervise(flow), name=f"login-{key}")
        await self._publish_login(flow)
        return flow

    async def submit_code(self, profile: Profile, code: str) -> LoginFlow:
        flow = self._logins.get(profile_key(profile))
        if flow is None or flow.state != "awaiting_code" or flow.master_fd is None:
            raise RuntimeError("no sign-in is waiting for a code")
        code = code.strip()
        if not code:
            raise ValueError("code is empty")
        flow.message = None
        flow.output = ""  # judge the reply to this code on its own
        os.write(flow.master_fd, code.encode() + b"\r")
        await self._publish_login(flow)
        return flow

    async def cancel_login(self, profile: Profile) -> None:
        flow = self._logins.get(profile_key(profile))
        if flow is None or not flow.active:
            return
        flow.state = "cancelled"
        self._terminate(flow)
        await self._publish_login(flow)

    def _on_output(self, flow: LoginFlow) -> None:
        if flow.master_fd is None:
            return
        try:
            chunk = os.read(flow.master_fd, 65536)
        except OSError:
            chunk = b""
        if not chunk:
            self._close_pty(flow)
            return
        if flow.absorb(chunk.decode("utf-8", errors="replace")):
            asyncio.create_task(self._publish_login(flow))

    async def _supervise(self, flow: LoginFlow) -> None:
        assert flow.process is not None
        try:
            returncode = await asyncio.wait_for(
                flow.process.wait(), LOGIN_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            if flow.active:
                flow.state = "failed"
                flow.message = "Sign-in timed out"
            self._terminate(flow)
            await self._publish_login(flow)
            return
        await asyncio.sleep(0.1)  # let the reader drain the final output
        self._close_pty(flow)
        if flow.state == "cancelled":
            return
        if returncode == 0:
            flow.state = "succeeded"
            flow.message = None
        else:
            flow.state = "failed"
            tail = _RE_ANSI.sub("", flow.output).strip().splitlines()
            flow.message = tail[-1].strip() if tail else f"exited with {returncode}"
        await self._publish_login(flow)
        await self.refresh(flow.profile)

    def _close_pty(self, flow: LoginFlow) -> None:
        if flow.master_fd is None:
            return
        try:
            asyncio.get_running_loop().remove_reader(flow.master_fd)
        except RuntimeError:
            pass
        try:
            os.close(flow.master_fd)
        except OSError:
            pass
        flow.master_fd = None

    def _terminate(self, flow: LoginFlow) -> None:
        process = flow.process
        if process is not None and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        self._close_pty(flow)

    # -- events --------------------------------------------------------

    async def _publish_login(self, flow: LoginFlow) -> None:
        await self._publish({"type": "account_login", **flow.to_payload()})

    async def _publish(self, event: dict[str, Any]) -> None:
        if self._bus is not None:
            await self._bus.publish(event)


account_manager = AccountManager()
