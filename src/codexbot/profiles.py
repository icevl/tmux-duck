"""Agent account profiles.

A profile is one set of agent credentials. Each non-default profile owns a
config directory that the agent is launched with — ``CLAUDE_CONFIG_DIR`` for
Claude Code — so its login, transcripts (``projects/``) and per-process
session files (``sessions/``) are isolated from every other account.

The default profile (id ``""``) is the system-wide login in ``~/.claude`` /
``~/.codex`` and needs no environment at all, so windows created before
profiles existed keep working unchanged.

Creating a Claude profile links the user's shared configuration (settings,
skills, plugins, agents, CLAUDE.md …) from ``~/.claude`` into the new
directory, and seeds ``.claude.json`` so first launch skips onboarding and
keeps the user's MCP servers. Only credentials and history stay separate.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import shutil
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import config
from .utils import atomic_write_json, codexbot_dir

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_ID = ""
SUPPORTED_RUNTIMES = ("claude",)

# Entries of ~/.claude shared into every Claude profile (when present).
_CLAUDE_SHARED_ENTRIES = (
    "settings.json",
    "CLAUDE.md",
    "skills",
    "agents",
    "commands",
    "output-styles",
    "plugins",
)
# Keys of ~/.claude.json copied into a new profile's .claude.json.
_CLAUDE_SEEDED_KEYS = (
    "hasCompletedOnboarding",
    "lastOnboardingVersion",
    "autoUpdates",
    "mcpServers",
)
_SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


@dataclass(frozen=True)
class Profile:
    id: str
    runtime: str
    label: str
    home: str | None = None  # None → the system default config dir

    @property
    def is_default(self) -> bool:
        return self.id == DEFAULT_PROFILE_ID

    def env(self) -> dict[str, str]:
        """Environment the agent (and its auth commands) must run with."""
        if self.home is None:
            return {}
        if self.runtime == "claude":
            return {"CLAUDE_CONFIG_DIR": self.home}
        return {}

    @property
    def claude_projects_path(self) -> Path:
        if self.home is None:
            return config.claude_projects_path
        return Path(self.home) / "projects"

    @property
    def claude_sessions_path(self) -> Path:
        if self.home is None:
            return config.claude_sessions_path
        return Path(self.home) / "sessions"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_profile(runtime: str) -> Profile:
    label = "Claude" if runtime == "claude" else "Codex"
    return Profile(id=DEFAULT_PROFILE_ID, runtime=runtime, label=label)


def _slugify(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:32].strip("-")
    return slug or "account"


class ProfileStore:
    """Profiles persisted in ``<codexbot_dir>/profiles.json``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._profiles: dict[str, Profile] | None = None

    @property
    def _state_file(self) -> Path:
        return codexbot_dir() / "profiles.json"

    @property
    def _homes_root(self) -> Path:
        return codexbot_dir() / "profiles"

    def _load(self) -> dict[str, Profile]:
        if self._profiles is not None:
            return self._profiles
        profiles: dict[str, Profile] = {}
        try:
            raw = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        for item in raw.get("profiles", []) if isinstance(raw, dict) else []:
            try:
                profile = Profile(
                    id=str(item["id"]),
                    runtime=str(item["runtime"]),
                    label=str(item["label"]),
                    home=str(item["home"]),
                )
            except (KeyError, TypeError):
                continue
            if _SAFE_ID_RE.match(profile.id) and profile.runtime in SUPPORTED_RUNTIMES:
                profiles[profile.id] = profile
        self._profiles = profiles
        return profiles

    def _save(self) -> None:
        profiles = self._profiles or {}
        atomic_write_json(
            self._state_file,
            {"profiles": [p.to_dict() for p in profiles.values()]},
        )

    def reload(self) -> None:
        with self._lock:
            self._profiles = None

    def list(self, runtime: str | None = None) -> list[Profile]:
        """Default profiles first, then custom ones in creation order."""
        with self._lock:
            custom = list(self._load().values())
        runtimes = [runtime] if runtime else ["claude", "codex"]
        result = [default_profile(r) for r in runtimes]
        result.extend(p for p in custom if runtime is None or p.runtime == runtime)
        return result

    def get(self, profile_id: str, runtime: str) -> Profile | None:
        if profile_id == DEFAULT_PROFILE_ID:
            return default_profile(runtime)
        with self._lock:
            profile = self._load().get(profile_id)
        if profile is None or profile.runtime != runtime:
            return None
        return profile

    def resolve(self, profile_id: str | None, runtime: str) -> Profile:
        """Like ``get`` but falls back to the default profile."""
        return self.get(profile_id or DEFAULT_PROFILE_ID, runtime) or default_profile(
            runtime
        )

    def create(self, runtime: str, label: str) -> Profile:
        if runtime not in SUPPORTED_RUNTIMES:
            raise ValueError(f"profiles are not supported for runtime {runtime!r}")
        label = label.strip()
        if not label:
            raise ValueError("label is required")
        with self._lock:
            profiles = self._load()
            if any(p.label.casefold() == label.casefold() for p in profiles.values()):
                raise ValueError(f"an account named {label!r} already exists")
            base = _slugify(label)
            profile_id = base
            while profile_id in profiles:
                profile_id = f"{base}-{secrets.token_hex(2)}"
            home = self._homes_root / profile_id
            home.mkdir(parents=True, exist_ok=True)
            _prepare_claude_home(home)
            profile = Profile(
                id=profile_id, runtime=runtime, label=label, home=str(home)
            )
            profiles[profile_id] = profile
            self._save()
        logger.info("Created %s profile %s at %s", runtime, profile_id, home)
        return profile

    def delete(self, profile_id: str) -> Profile | None:
        """Forget a profile and remove its config directory."""
        with self._lock:
            profiles = self._load()
            profile = profiles.pop(profile_id, None)
            if profile is None:
                return None
            self._save()
        home = Path(profile.home) if profile.home else None
        if home is not None and home.is_relative_to(self._homes_root):
            shutil.rmtree(home, ignore_errors=True)
        logger.info("Deleted profile %s", profile_id)
        return profile


def _prepare_claude_home(home: Path) -> None:
    source = config.claude_projects_path.parent  # ~/.claude
    for name in _CLAUDE_SHARED_ENTRIES:
        target = source / name
        link = home / name
        if not target.exists() or link.exists() or link.is_symlink():
            continue
        try:
            link.symlink_to(target)
        except OSError as e:
            logger.warning("Could not link %s into %s: %s", target, home, e)

    state_file = home / ".claude.json"
    if state_file.exists():
        return
    seeded: dict[str, Any] = {"hasCompletedOnboarding": True}
    try:
        global_state = json.loads(
            (Path.home() / ".claude.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        global_state = {}
    if isinstance(global_state, dict):
        for key in _CLAUDE_SEEDED_KEYS:
            if key in global_state:
                seeded[key] = global_state[key]
    atomic_write_json(state_file, seeded)


profile_store = ProfileStore()
