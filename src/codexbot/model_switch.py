"""Model / reasoning-effort switching for a running agent session.

The two CLIs differ in what they allow mid-session:

- Claude Code takes ``/model <alias>`` and ``/effort <level>`` as one-line
  commands and applies them to the running conversation (it also saves the
  choice as the default for new sessions — that is the CLI's behaviour).
- Codex only offers an interactive ``/model`` picker, so the session is
  relaunched in the same tmux window with ``codex resume <id> -m <model>
  -c model_reasoning_effort=<effort>``. The conversation carries over and
  the window id (all routing) stays the same; the flags apply to that
  launch only, without touching ``config.toml``.

The current model itself is read from the transcript (``transcript_meta``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import config
from .runtimes import get_runtime
from .runtimes.codex import CodexRuntime
from .tmux_manager import tmux_manager

logger = logging.getLogger(__name__)

# Claude Code models by explicit id, so the picker shows versions (the bare
# aliases "opus"/"sonnet" resolve to whatever is newest). `[1m]` selects the
# 1M-context window; of these only Opus 5.5 accepts it (checked against
# Claude Code 2.1.283 — Haiku rejects it, Sonnet/Fable ignore it).
CLAUDE_MODELS: tuple[tuple[str, str], ...] = (
    ("claude-opus-5-5[1m]", "Opus 5.5 · 1M context"),
    ("claude-opus-5-5", "Opus 5.5"),
    ("claude-fable-5-1", "Fable 5.1"),
    ("claude-sonnet-5", "Sonnet 5"),
    ("claude-haiku-4-5", "Haiku 4.5"),
    ("claude-opus-5", "Opus 5"),
    ("claude-fable-5", "Fable 5"),
)
CLAUDE_EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")

# Used when Codex's own model list (`models_cache.json`) is unreadable.
CODEX_FALLBACK_MODELS: tuple[tuple[str, str], ...] = (
    ("gpt-5.5", "GPT-5.5"),
    ("gpt-5.4", "gpt-5.4"),
    ("gpt-5.4-mini", "GPT-5.4-Mini"),
    ("gpt-5.3-codex", "gpt-5.3-codex"),
)
CODEX_EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh")

# Seconds to wait for Codex to exit before relaunching it.
CODEX_EXIT_TIMEOUT = 10.0
# Pause between Claude's `/model` and `/effort` so the first one is handled
# before the second is typed.
CLAUDE_COMMAND_GAP = 1.0

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-\[\]]{0,63}$")


class ModelSwitchError(Exception):
    """A switch request that cannot be carried out (bad input or state)."""


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    efforts: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "efforts": list(self.efforts)}


def _codex_models_cache_path() -> Path:
    return config.codex_sessions_path.parent / "models_cache.json"


def _codex_models() -> list[ModelOption]:
    try:
        data = json.loads(_codex_models_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    options: list[ModelOption] = []
    models = data.get("models") if isinstance(data, dict) else None
    for model in models if isinstance(models, list) else []:
        if not isinstance(model, dict) or model.get("visibility") != "list":
            continue
        slug = model.get("slug")
        if not isinstance(slug, str) or not _SAFE_VALUE.match(slug):
            continue
        label = model.get("display_name")
        levels = model.get("supported_reasoning_levels")
        efforts = tuple(
            lvl["effort"]
            for lvl in (levels if isinstance(levels, list) else [])
            if isinstance(lvl, dict) and isinstance(lvl.get("effort"), str)
        )
        options.append(
            ModelOption(
                id=slug,
                label=label if isinstance(label, str) and label else slug,
                efforts=efforts or CODEX_EFFORTS,
            )
        )
    if options:
        return options
    return [ModelOption(i, label, CODEX_EFFORTS) for i, label in CODEX_FALLBACK_MODELS]


def model_catalog(runtime: str) -> dict[str, Any]:
    """Models and effort levels the UI can offer for ``runtime``."""
    if runtime == "claude":
        models = [ModelOption(i, label, CLAUDE_EFFORTS) for i, label in CLAUDE_MODELS]
        restarts = False
    else:
        models = _codex_models()
        restarts = True
    return {
        "runtime": runtime,
        "models": [m.to_payload() for m in models],
        # Whether a switch relaunches the agent (the UI warns about it).
        "restarts": restarts,
    }


def _validate(value: str | None, what: str) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _SAFE_VALUE.match(value):
        raise ModelSwitchError(f"invalid {what}: {value!r}")
    return value


async def switch_claude(window_id: str, model: str | None, effort: str | None) -> None:
    commands = []
    if model:
        commands.append(f"/model {model}")
    if effort:
        commands.append(f"/effort {effort}")
    for i, command in enumerate(commands):
        if i:
            await asyncio.sleep(CLAUDE_COMMAND_GAP)
        if not await tmux_manager.send_keys(window_id, command):
            raise ModelSwitchError("failed to send the command to the session")


async def _pane_runs_codex(window_id: str) -> bool:
    tmux_manager.invalidate_windows_cache()
    window = await tmux_manager.find_window_by_id(window_id)
    if window is None:
        raise ModelSwitchError("window not found")
    return CodexRuntime().pane_command_matches(window.pane_current_command)


async def _wait_codex_exit(window_id: str, timeout: float) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if not await _pane_runs_codex(window_id):
            return True
        await asyncio.sleep(0.3)
    return False


def codex_restart_command(
    session_id: str, model: str | None, effort: str | None
) -> str:
    cmd = get_runtime("codex").build_start_command(session_id)
    if model:
        cmd = f"{cmd} -m {shlex.quote(model)}"
    if effort:
        cmd = f"{cmd} -c {shlex.quote(f'model_reasoning_effort={effort}')}"
    return cmd


async def switch_codex(
    window_id: str, session_id: str | None, model: str | None, effort: str | None
) -> None:
    if not session_id:
        raise ModelSwitchError("session not detected yet — send a message first")
    if await _pane_runs_codex(window_id):
        # `/quit` is Codex's own clean exit; Ctrl+C twice is the fallback for
        # a TUI that ignores it (e.g. a popup has focus).
        await tmux_manager.send_keys(window_id, "/quit")
        if not await _wait_codex_exit(window_id, CODEX_EXIT_TIMEOUT / 2):
            for _ in range(2):
                await tmux_manager.send_keys(
                    window_id, "C-c", enter=False, literal=False
                )
                await asyncio.sleep(0.3)
            if not await _wait_codex_exit(window_id, CODEX_EXIT_TIMEOUT / 2):
                raise ModelSwitchError("Codex did not exit; switch aborted")
    cmd = codex_restart_command(session_id, model, effort)
    logger.info("Relaunching Codex in %s: %s", window_id, cmd)
    if not await tmux_manager.type_start_command(window_id, cmd, get_runtime("codex")):
        raise ModelSwitchError("failed to relaunch Codex")


async def switch_model(
    window_id: str,
    runtime: str,
    session_id: str | None,
    model: str | None,
    effort: str | None,
) -> None:
    model = _validate(model, "model")
    effort = _validate(effort, "effort")
    if not model and not effort:
        raise ModelSwitchError("nothing to switch")
    if runtime == "claude":
        await switch_claude(window_id, model, effort)
    else:
        await switch_codex(window_id, session_id, model, effort)
