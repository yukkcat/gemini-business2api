"""
gemini-refresh-worker entry point.

- Loads environment variables, initializes storage backend
- Installs child_reaper (cleans up Chromium zombie processes)
- Starts the async polling loop (RefreshService.start_polling)
- Optionally starts a minimal HTTP health check server
- Handles SIGTERM/SIGINT for graceful shutdown
"""

import asyncio
import logging
import os
import signal
import sys
from asyncio import StreamReader, StreamWriter

from dotenv import load_dotenv

load_dotenv()

# ---- logging setup ----

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("worker")


# ---- health check server ----

async def _handle_health(reader: StreamReader, writer: StreamWriter) -> None:
    """Minimal HTTP health check handler."""
    try:
        await reader.read(4096)
        body = b'{"status":"ok"}'
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n"
            b"\r\n" + body
        )
        writer.write(response)
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def start_health_server(port: int) -> asyncio.AbstractServer:
    server = await asyncio.start_server(_handle_health, "0.0.0.0", port)
    logger.info("[HEALTH] listening on port %d", port)
    return server


# ---- main ----

async def main() -> None:
    logger.info("=" * 50)
    logger.info("gemini-refresh-worker starting")
    logger.info("=" * 50)

    # Install child reaper (Linux only, cleans up Chromium zombies)
    from worker.child_reaper import install_child_reaper
    if install_child_reaper(log=lambda msg: logger.info(msg)):
        logger.info("[INIT] child reaper installed")
    else:
        logger.info("[INIT] child reaper not needed (non-POSIX or no SIGCHLD)")

    # Initialize storage backend (database or remote project)
    from worker import storage
    if not storage.is_database_enabled():
        logger.error("[INIT] storage backend not configured, set DATABASE_URL or REMOTE_PROJECT_BASE_URL")
        sys.exit(1)
    logger.info("[INIT] storage backend: %s", storage.get_storage_mode())

    # Initialize config (reads from storage backend)
    # This import triggers ConfigManager.__init__ which calls storage
    from worker.config import config
    logger.info(
        "[INIT] config loaded — scheduled_refresh_enabled=%s, interval=%d min, browser_mode=%s, headless=%s, window=%dh",
        config.retry.scheduled_refresh_enabled,
        config.retry.scheduled_refresh_interval_minutes,
        config.basic.browser_mode,
        config.basic.browser_headless,
        config.basic.refresh_window_hours,
    )
    logger.info(
        "[INIT] account management — delete_expired=%s, auto_register=%s, min_count=%d",
        config.retry.delete_expired_accounts,
        config.retry.auto_register_enabled,
        config.retry.min_account_count,
    )
    logger.info("[INIT] business config source: %s", storage.get_storage_mode())
    logger.info("[INIT] env is only used for bootstrap settings (remote URL/password, logging, health)")

    # Create refresh service
    from worker.refresh_service import RefreshService
    service = RefreshService()

    # Optional health check server
    health_server = None
    health_port = int(os.getenv("HEALTH_PORT", "0"))
    if health_port > 0:
        health_server = await start_health_server(health_port)

    # Graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _shutdown_handler():
        logger.info("[SHUTDOWN] signal received, stopping...")
        service.stop_polling()
        stop_event.set()

    # Install signal handlers (POSIX only; on Windows use KeyboardInterrupt)
    if os.name == "posix":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _shutdown_handler)

    # Start polling
    polling_task = asyncio.create_task(service.start_polling())

    # Wait for shutdown signal
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        _shutdown_handler()

    # Clean up
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass

    if health_server:
        health_server.close()
        await health_server.wait_closed()

    logger.info("[SHUTDOWN] worker stopped")


if __name__ == "__main__":
    from worker.local_lock import LocalFileLock

    process_lock = LocalFileLock(os.path.join("data", "worker-main.lock"))
    if not process_lock.acquire(blocking=False):
        logger.error("[INIT] another worker.main process is already running")
        sys.exit(1)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        process_lock.release()
