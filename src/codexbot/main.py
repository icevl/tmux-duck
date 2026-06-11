"""Application entry point for CodexBot.

Configures logging, initializes the tmux session, and starts Telegram polling
— or, when ``CODEXBOT_TELEGRAM_ENABLED=false``, a headless loop that runs only
the external connectors (e.g. Slack) with no Telegram or web UI.
"""

import asyncio
import logging
import signal
import sys

from .utils import SingleInstanceLock, codexbot_dir


async def _run_headless(logger: logging.Logger) -> None:
    """Run connectors only — no Telegram polling, no web UI.

    Starts the tmux session, the transcript monitor, a loopback approval
    server (so the Claude write-gate works without the web UI), and the
    connector manager; then idles until SIGINT/SIGTERM.
    """
    from .config import config
    from .connectors import connector_manager
    from .connectors.approval_server import ApprovalServer
    from .session_monitor import SessionMonitor
    from .tmux_manager import tmux_manager

    session = tmux_manager.get_or_create_session()
    logger.info("Tmux session '%s' ready", session.session_name)

    monitor = SessionMonitor()
    monitor.start()
    logger.info("Session monitor started")

    approval = ApprovalServer(port=config.web_ui_port)
    await approval.start()

    await connector_manager.start(monitor, bot=None)
    logger.info("Headless mode active — Telegram and web UI disabled.")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - non-unix
            pass
    try:
        await stop.wait()
    finally:
        logger.info("Shutting down headless mode…")
        await connector_manager.stop()
        await approval.stop()
        await monitor.stop()


def main() -> None:
    """Main entry point."""
    lock = SingleInstanceLock(codexbot_dir() / "codexbot.lock")
    if not lock.acquire():
        holder = f" (pid={lock.holder_pid})" if lock.holder_pid else ""
        print(f"Error: another codexbot instance is already running{holder}.")
        sys.exit(1)

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    try:
        try:
            from .config import config
        except ValueError as e:
            config_dir = codexbot_dir()
            env_path = config_dir / ".env"
            print(f"Error: {e}\n")
            print(f"Create {env_path} with the following content:\n")
            print("  TELEGRAM_BOT_TOKEN=your_bot_token_here")
            print("  ALLOWED_USERS=your_telegram_user_id")
            print()
            print("Get your bot token from @BotFather on Telegram.")
            print("Get your user ID from @userinfobot on Telegram.")
            sys.exit(1)

        root_level = logging._nameToLevel.get(config.log_level, logging.INFO)
        logging.getLogger().setLevel(root_level)
        logging.getLogger("codexbot").setLevel(root_level)
        logging.getLogger("telegram.ext.AIORateLimiter").setLevel(logging.INFO)
        logger = logging.getLogger(__name__)

        logger.info("Codex sessions path: %s", config.codex_sessions_path)

        if not config.telegram_enabled:
            logger.info("Telegram disabled — starting in headless connector mode")
            asyncio.run(_run_headless(logger))
            return

        from .tmux_manager import tmux_manager

        logger.info("Allowed users: %s", config.allowed_users)
        session = tmux_manager.get_or_create_session()
        logger.info("Tmux session '%s' ready", session.session_name)

        logger.info("Starting Telegram bot...")
        from .bot import create_bot

        application = create_bot()
        application.run_polling(allowed_updates=["message", "callback_query"])
    finally:
        lock.release()


if __name__ == "__main__":
    main()
