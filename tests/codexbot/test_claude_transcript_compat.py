"""Claude Code 2.1.x transcript and pane formats.

Record shapes mirror what Claude Code 2.1.282 writes to
``~/.claude/projects/<slug>/<uuid>.jsonl`` and draws in its tmux pane.
"""

import json
from unittest.mock import patch

import pytest

from codexbot.connectors.classifier import classify_action
from codexbot.monitor_state import TrackedSession
from codexbot.runtimes.claude import ClaudeRuntime
from codexbot.session_monitor import SessionInfo, SessionMonitor
from codexbot.terminal_parser import parse_status_line
from codexbot.transcript_parser import TranscriptParser

TS = "2026-09-25T15:25:51.617Z"


def _user(content, **extra):
    return {
        "type": "user",
        "timestamp": TS,
        "message": {"role": "user", "content": content},
        **extra,
    }


def _assistant(*blocks):
    return {
        "type": "assistant",
        "timestamp": TS,
        "message": {"role": "assistant", "content": list(blocks)},
    }


def _text(text):
    return {"type": "text", "text": text}


def _system(subtype, **extra):
    return {"type": "system", "subtype": subtype, "timestamp": TS, **extra}


def _queued(prompt, mode="prompt", origin=None):
    attachment = {"type": "queued_command", "prompt": prompt, "commandMode": mode}
    if origin is not None:
        attachment["origin"] = origin
    return {"type": "attachment", "timestamp": TS, "attachment": attachment}


def _turn_end():
    return _system("turn_duration", durationMs=3344, messageCount=18)


def _parse(*records):
    entries, _ = TranscriptParser.parse_entries(list(records))
    return entries


class TestHiddenHarnessRecords:
    @pytest.mark.parametrize(
        "record",
        [
            pytest.param(
                _user(
                    "[Image: original 2444x1648, displayed at 2000x1349.]", isMeta=True
                ),
                id="meta",
            ),
            pytest.param(
                _user(
                    "This session is being continued from a previous conversation…",
                    isCompactSummary=True,
                    isVisibleInTranscriptOnly=True,
                ),
                id="compact_summary",
            ),
            pytest.param(
                {
                    "type": "attachment",
                    "timestamp": TS,
                    "attachment": {"type": "total_tokens_reminder"},
                },
                id="context_attachment",
            ),
            pytest.param(
                {"type": "ai-title", "aiTitle": "Conversation recall"}, id="metadata"
            ),
        ],
    )
    def test_not_rendered(self, record):
        assert _parse(record) == []

    def test_real_prompt_still_rendered(self):
        [entry] = _parse(_user("привет", origin={"kind": "human"}))
        assert (entry.role, entry.content_type, entry.text) == (
            "user",
            "text",
            "привет",
        )
        assert entry.starts_turn is None


class TestInterrupt:
    @pytest.mark.parametrize(
        "marker",
        ["[Request interrupted by user]", "[Request interrupted by user for tool use]"],
    )
    def test_interrupt_ends_turn(self, marker):
        entries = _parse(_user([_text(marker)]))
        assert [(e.content_type, e.text) for e in entries] == [
            ("system", "⏹ Interrupted"),
            ("completion", ""),
        ]


class TestQueuedPrompt:
    def test_mid_turn_prompt_is_a_user_message_that_keeps_the_turn(self):
        [entry] = _parse(_queued("а ещё добавь тест", origin={"kind": "human"}))
        assert (entry.role, entry.text) == ("user", "а ещё добавь тест")
        assert entry.starts_turn is False

    def test_task_notification_is_a_notice(self):
        prompt = (
            "<task-notification>\n<task-id>a1</task-id>\n<status>completed</status>\n"
            '<summary>Agent "Explore" finished</summary>\n</task-notification>'
        )
        [entry] = _parse(_queued(prompt, mode="task-notification"))
        assert (entry.role, entry.content_type) == ("assistant", "system")
        assert entry.text == '🔔 Agent "Explore" finished'
        assert not entry.starts_turn

    def test_peer_message_unwraps_agent_envelope(self):
        [entry] = _parse(
            _queued(
                '<agent-message from="general-purpose">\nrelay this\n</agent-message>',
                origin={"kind": "peer", "name": "general-purpose"},
            )
        )
        assert entry.content_type == "system"
        assert entry.text.startswith("✉️ Message from general-purpose")
        assert "agent-message" not in entry.text
        assert "relay this" in entry.text


class TestTaskNotificationPrompt:
    def test_idle_notification_opens_a_turn_as_a_notice(self):
        [entry] = _parse(
            _user(
                "<task-notification>\n<status>failed</status>\n</task-notification>",
                origin={"kind": "task-notification"},
            )
        )
        assert (entry.role, entry.content_type) == ("assistant", "system")
        assert entry.text == "🔔 Background task failed"
        assert entry.starts_turn is True


class TestSystemRecords:
    def test_compact_boundary(self):
        [entry] = _parse(
            _system(
                "compact_boundary",
                content="Conversation compacted",
                compactMetadata={
                    "trigger": "auto",
                    "preTokens": 1000192,
                    "postTokens": 12934,
                },
            )
        )
        assert (
            entry.text == "🗜 Conversation compacted (auto): 1,000,192 → 12,934 tokens"
        )

    def test_api_error_with_retry(self):
        [entry] = _parse(
            _system(
                "api_error",
                error={"formatted": "Unable to connect to API (ConnectionRefused)"},
                retryAttempt=1,
                maxRetries=10,
            )
        )
        assert (
            entry.text
            == "⚠️ API error: Unable to connect to API (ConnectionRefused) — retry 1/10"
        )

    def test_scheduled_wakeup_opens_a_turn(self):
        [entry] = _parse(
            _system(
                "scheduled_task_fire",
                content="Claude resuming /loop wakeup (Jul 29 9:10am)",
            )
        )
        assert entry.text == "⏰ Claude resuming /loop wakeup (Jul 29 9:10am)"
        assert entry.starts_turn is True

    def test_away_summary_and_model_fallback(self):
        entries = _parse(
            _system("away_summary", content="Recap of the session"),
            _system("model_refusal_fallback", content="Switched to Opus 4.8."),
        )
        assert [e.text for e in entries] == [
            "📝 Recap of the session",
            "⚠️ Switched to Opus 4.8.",
        ]

    def test_local_command_stdout_from_system_record(self):
        entries = _parse(
            _user("<command-name>/model</command-name>\n<command-args></command-args>"),
            _system(
                "local_command",
                content="<local-command-stdout>Set model to \x1b[1mFable 5\x1b[22m</local-command-stdout>",
            ),
        )
        assert [(e.content_type, e.text) for e in entries] == [
            ("local_command", "❯ `/model`\n`Set model to Fable 5`")
        ]

    def test_local_command_without_output_shows_the_command(self):
        entries = _parse(
            _user("<command-name>/clear</command-name>"),
            _system(
                "local_command", content="<local-command-stdout></local-command-stdout>"
            ),
        )
        assert [e.text for e in entries] == ["❯ `/clear`"]


class TestStructuredPatch:
    def _edit_records(self, name, tool_input, tool_use_result):
        return (
            _assistant(
                {"type": "tool_use", "id": "toolu_1", "name": name, "input": tool_input}
            ),
            _user(
                [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}],
                toolUseResult=tool_use_result,
            ),
        )

    def test_edit_diff_comes_from_structured_patch(self):
        patch_hunks = [
            {
                "oldStart": 10,
                "oldLines": 2,
                "newStart": 10,
                "newLines": 1,
                "lines": [" keep", "-gone", "-gone2", "+new"],
            }
        ]
        [_, result] = _parse(
            *self._edit_records(
                "Edit",
                {
                    "file_path": "/a.py",
                    "old_string": "gone\ngone2",
                    "new_string": "new",
                },
                {"filePath": "/a.py", "structuredPatch": patch_hunks},
            )
        )
        assert "Added 1 lines, removed 2 lines" in result.text
        assert "@@ -10,2 +10,1 @@" in result.text

    def test_deletion_only_edit_gets_a_diff(self):
        patch_hunks = [
            {
                "oldStart": 3,
                "oldLines": 1,
                "newStart": 2,
                "newLines": 0,
                "lines": ["-dead code"],
            }
        ]
        [_, result] = _parse(
            *self._edit_records(
                "Edit",
                {"file_path": "/a.py", "old_string": "dead code", "new_string": ""},
                {"structuredPatch": patch_hunks},
            )
        )
        assert "Added 0 lines, removed 1 lines" in result.text

    def test_write_create_counts_written_lines(self):
        [_, result] = _parse(
            *self._edit_records(
                "Write",
                {"file_path": "/b.py", "content": "a\nb\nc\n"},
                {"type": "create", "content": "a\nb\nc\n", "structuredPatch": []},
            )
        )
        assert "Wrote 3 lines" in result.text

    def test_write_update_renders_diff(self):
        [_, result] = _parse(
            *self._edit_records(
                "Write",
                {"file_path": "/b.py", "content": "x\n"},
                {
                    "type": "update",
                    "structuredPatch": [
                        {
                            "oldStart": 1,
                            "oldLines": 1,
                            "newStart": 1,
                            "newLines": 1,
                            "lines": ["-a", "+x"],
                        }
                    ],
                },
            )
        )
        assert "Added 1 lines, removed 1 lines" in result.text


class TestAgentTool:
    def test_agent_summary_uses_description(self):
        summary = TranscriptParser.format_tool_use_summary(
            "Agent",
            {
                "description": "Find the parser",
                "prompt": "long…",
                "subagent_type": "Explore",
            },
        )
        assert summary == "**Agent**(Find the parser)"


class TestMonitorTurnLifecycle:
    async def _run(self, tmp_path, records):
        monitor = SessionMonitor(
            projects_path=tmp_path / "projects",
            state_file=tmp_path / "monitor_state.json",
        )
        jsonl_file = tmp_path / "session.jsonl"
        jsonl_file.write_text(
            "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
        )
        monitor.state.update_session(
            TrackedSession(
                session_id="s", file_path=str(jsonl_file), last_byte_offset=0
            )
        )
        with patch.object(
            monitor,
            "_resolve_active_sessions",
            return_value=[SessionInfo(session_id="s", file_path=jsonl_file)],
        ):
            return await monitor.check_for_updates({"s"}, bootstrap=False)

    @pytest.mark.asyncio
    async def test_queued_prompt_does_not_complete_the_running_turn(self, tmp_path):
        messages = await self._run(
            tmp_path,
            [
                _user("сделай рефакторинг"),
                _assistant(_text("начинаю")),
                _queued("и тесты не забудь", origin={"kind": "human"}),
                _assistant(_text("готово")),
                _turn_end(),
            ],
        )
        kinds = [(m.message_type, m.role, m.text) for m in messages]
        assert kinds == [
            ("content", "user", "сделай рефакторинг"),
            ("content", "assistant", "начинаю"),
            ("content", "user", "и тесты не забудь"),
            ("content", "assistant", "готово"),
            ("completion", "assistant", ""),
        ]

    @pytest.mark.asyncio
    async def test_interrupt_completes_the_turn(self, tmp_path):
        messages = await self._run(
            tmp_path,
            [
                _user("запусти сборку"),
                _assistant(
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Bash",
                        "input": {"command": "make"},
                    }
                ),
                _user([_text("[Request interrupted by user]")]),
            ],
        )
        assert [m.message_type for m in messages][-1] == "completion"
        assert not [m for m in messages if m.role == "user" and "interrupted" in m.text]

    @pytest.mark.asyncio
    async def test_notification_turn_completes_separately(self, tmp_path):
        messages = await self._run(
            tmp_path,
            [
                _user("запусти агента в фоне"),
                _assistant(_text("запустил")),
                _turn_end(),
                _user(
                    "<task-notification>\n<summary>Agent finished</summary>\n</task-notification>",
                    origin={"kind": "task-notification"},
                ),
                _assistant(_text("агент закончил")),
                _turn_end(),
            ],
        )
        completions = [m.turn_id for m in messages if m.message_type == "completion"]
        assert completions == [1, 2]


class TestStatusLine:
    CHROME = (
        "─" * 43
        + "\n❯ \n"
        + "─" * 43
        + "\n  ⏵⏵ bypass permissions on (shift+tab to cycle)"
    )

    def test_live_status_with_tip_rows(self):
        pane = (
            "⏺ Bash(ls)\n"
            "✽ Billowing… (1m 52s · ↓ 8.8k tokens)\n"
            "  ⎿  Tip: Use /btw to ask a quick side\n"
            "     question without interrupting Claude's\n"
            "     current work\n\n" + self.CHROME
        )
        assert parse_status_line(pane) == "Billowing… (1m 52s · ↓ 8.8k tokens)"

    def test_live_status_with_task_list(self):
        pane = (
            "✻ Inferring… (12s · ↑ 1.2k tokens)\n"
            "  ⎿  ◼ Fix the parser\n"
            "     ◻ Write tests\n\n" + self.CHROME
        )
        assert parse_status_line(pane) == "Inferring… (12s · ↑ 1.2k tokens)"

    def test_finished_footer_is_idle(self):
        pane = "⏺ Готово.\n\n✻ Cooked for 3m 2s\n\n" + self.CHROME
        assert parse_status_line(pane) is None

    def test_indented_output_above_idle_prompt(self):
        pane = "⏺ Bash(ls)\n  ⎿  a.txt\n     b.txt\n\n" + self.CHROME
        assert parse_status_line(pane) is None


class TestPaneCommand:
    @pytest.mark.parametrize("cmd", ["claude", "2.1.282", "10.0.1"])
    def test_matches_claude(self, cmd):
        assert ClaudeRuntime().pane_command_matches(cmd)

    @pytest.mark.parametrize("cmd", ["zsh", "codex", "node", "python3.13", "2.1"])
    def test_rejects_other(self, cmd):
        assert not ClaudeRuntime().pane_command_matches(cmd)


class TestMonitorToolGate:
    def test_monitor_command_is_classified_as_shell(self):
        assert classify_action("Monitor", {"command": "rm -rf build"}) == "write"
        assert classify_action("Monitor", {"command": "tail -f app.log"}) == "read"

    def test_monitor_without_command_is_read(self):
        assert classify_action("Monitor", {"agentId": "a1"}) == "read"


# Pane snapshots captured from Claude Code 2.1.283 (paths shortened).
PLAN_PANE = """\
  ────────────────────────────────────────────────────────────
   Ready to code?
   Here is Claude's plan:
  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
   Add README.md to repo
   Steps
   1. Create README.md at the repo root.
   2. Verify the file was created correctly.
  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  ────────────────────────────────────────────────────────────
   Claude has written up a plan and is ready to execute. Would you like to proceed?
   ❯ 1. Yes, auto-accept edits
     2. Yes, manually approve edits
     3. Tell Claude what to change
        shift+tab to approve with this feedback
   ctrl+g to edit in Vim · ~/.claude/plans/velvet-bird.md
"""

ASK_PANE = """\
❯ Ask me which color I prefer.
────────────────────────────────────────────────────────────
 ☐ Color
Which color do you prefer?
❯ 1. Red
     A bold, warm color
  2. Green
     A calming, natural color
  3. Type something.
────────────────────────────────────────────────────────────
  4. Chat about this
Enter to select · ↑/↓ to navigate · Esc to cancel
"""

BASH_PERMISSION_PANE = """\
 Bash command
   echo hello > a.txt
   Create a file with "hello" content
 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and always allow access to /work from this project
   3. No
 Esc to cancel · Tab to amend
"""

TRUST_PANE = """\
 Accessing workspace:
 /work
 Quick safety check: Is this a project you created or one you trust? (Like your own code,
 a well-known open source project, or work from your team).
 Claude Code'll be able to read, edit, and execute files here.
 Security guide
 ❯ No, exit
   Yes, I trust this folder
 Enter to confirm · Esc to cancel
"""


class TestInteractivePrompts:
    @pytest.mark.parametrize(
        ("pane", "name", "labels"),
        [
            pytest.param(
                PLAN_PANE,
                "ExitPlanMode",
                [
                    "Yes, auto-accept edits",
                    "Yes, manually approve edits",
                    "Tell Claude what to change",
                ],
                id="plan",
            ),
            pytest.param(
                ASK_PANE,
                "AskUserQuestion",
                ["Red", "Green", "Type something.", "Chat about this"],
                id="ask",
            ),
            pytest.param(
                BASH_PERMISSION_PANE,
                "PermissionPrompt",
                [
                    "Yes",
                    "Yes, and always allow access to /work from this project",
                    "No",
                ],
                id="bash_permission",
            ),
        ],
    )
    def test_detected_with_options(self, pane, name, labels):
        from codexbot.terminal_parser import extract_interactive_content, parse_options

        content = extract_interactive_content(pane, runtime="claude")
        assert content is not None and content.name == name
        parsed = parse_options(content.content)
        assert parsed is not None
        assert [o.label for o in parsed.options] == labels

    def test_trust_prompt_detected(self):
        from codexbot.terminal_parser import extract_interactive_content

        content = extract_interactive_content(TRUST_PANE, runtime="claude")
        assert content is not None and content.name == "WorkspaceTrust"


class TestStartupPrompts:
    def test_unnumbered_trust_moves_cursor_to_yes(self):
        from codexbot.runtimes.claude import _startup_prompt

        assert _startup_prompt(TRUST_PANE) == ("workspace_trust", ["Down", "Enter"])

    @pytest.mark.parametrize(
        ("pane", "expected"),
        [
            pytest.param(
                "Do you trust the files in this folder?\n\n❯ 1. Yes, proceed\n  2. No, exit\n",
                ("workspace_trust", ["Enter"]),
                id="legacy_trust",
            ),
            pytest.param(
                "WARNING: Claude Code running in Bypass Permissions mode\n\n"
                "❯ 1. No, exit\n  2. Yes, I accept\n",
                ("bypass_permissions", ["Down", "Enter"]),
                id="bypass",
            ),
            pytest.param(
                "bypass permissions mode\n 1. No\n ❯ 2. Yes, I accept",
                ("bypass_permissions", ["Enter"]),
                id="bypass_cursor_on_yes",
            ),
        ],
    )
    def test_keys(self, pane, expected):
        from codexbot.runtimes.claude import _startup_prompt

        assert _startup_prompt(pane) == expected

    @pytest.mark.parametrize("pane", [BASH_PERMISSION_PANE, PLAN_PANE, ASK_PANE])
    def test_working_prompts_are_not_startup_prompts(self, pane):
        from codexbot.runtimes.claude import _startup_prompt

        assert _startup_prompt(pane) is None


SEPARATOR = "─" * 40


class TestLiveStatusFromProbe:
    def test_status_with_background_hint_and_footer(self):
        pane = (
            "⏺ Sleeping for 40 seconds · 19s\n"
            "  ⎿  $ python3 -c 'import time; time.sleep(40)' (8s)\n"
            "     (ctrl+b ctrl+b (twice) to run in background)\n"
            "· Caramelizing… (10s · ↓ 186 tokens)\n"
            + SEPARATOR
            + "\n❯ \n"
            + SEPARATOR
            + "\n  ⏸ manual mode on · esc to interrupt · ← for agents\n"
        )
        assert parse_status_line(pane) == "Caramelizing… (10s · ↓ 186 tokens)"

    def test_done_footer_is_idle(self):
        pane = f"⏺ Done.\n\n✻ Baked for 3s · done 10:16 AM\n\n{SEPARATOR}\n❯ \n{SEPARATOR}\n"
        assert parse_status_line(pane) is None
