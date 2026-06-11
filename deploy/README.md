# Headless deploy (Slack connector only — no Telegram/web)

Runs codexbot with `CODEXBOT_TELEGRAM_ENABLED=false`: tmux session + transcript
monitor + a loopback approval server + the connector manager. No Telegram bot,
no web UI.

## Prerequisites on the host
- `tmux`, `uv`, `git`
- The agent CLI used by the connector (`claude` and/or `codex`) **installed and
  authenticated for the run user** — the agent executes on this host.
- The connector's `cwd` must be a real path on this host.

## Steps
1. `git clone https://github.com/icevl/tmux-duck.git /home/wavix/technical-assistant`
2. `cd /home/wavix/technical-assistant && uv sync`
3. `.env` (repo root): `CODEXBOT_TELEGRAM_ENABLED=false` and `CODEXBOT_SEARCH_ENABLED=false`
4. Import the connector (edit tokens + cwd first):
   `uv run codexbot-connectors import deploy/slack-connector.example.json`
5. Install supervisor unit: copy `deploy/supervisor/technical-assistant.conf` to
   `/etc/supervisor/conf.d/`, then `supervisorctl reread && supervisorctl update`.
6. Start: `supervisorctl start technical-assistant` (or set autostart=true).

## Notes
- torch is still a default dependency (pulled by `uv sync`) but unused in this
  mode; trimming it into an optional `search` extra is a possible follow-up.
- Manage connectors headlessly: `uv run codexbot-connectors {list,export,import,enable,disable,rm}`.
