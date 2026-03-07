"""
Interactive CLI for gemini-refresh-worker.

Use cases:
- Local interactive operation (Chinese menu)
- Manual one-shot refresh
- Remote project connectivity check
- Simple .env wizard for remote mode
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Tuple

from dotenv import load_dotenv

load_dotenv()


def _setup_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def _mask_secret(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def _env_path() -> Path:
    return Path(".env")


def _read_env_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _upsert_env(lines: list[str], key: str, value: str) -> list[str]:
    key_prefix = f"{key}="
    updated = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue
        if line.startswith(key_prefix):
            out.append(f"{key}={value}")
            updated = True
        else:
            out.append(line)
    if not updated:
        out.append(f"{key}={value}")
    return out


def _save_env_updates(updates: Dict[str, str]) -> Path:
    path = _env_path()
    lines = _read_env_lines(path)
    for key, value in updates.items():
        lines = _upsert_env(lines, key, value)
    text = "\n".join(lines).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def _print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def show_current_config() -> None:
    _print_header("当前配置概览")
    print(f"REMOTE_PROJECT_BASE_URL: {os.getenv('REMOTE_PROJECT_BASE_URL', '').strip() or '(not set)'}")
    print(f"REMOTE_PROJECT_PASSWORD: {_mask_secret(os.getenv('REMOTE_PROJECT_PASSWORD', '').strip())}")
    print(f"FORCE_REFRESH_ENABLED: {os.getenv('FORCE_REFRESH_ENABLED', '(not set)')}")
    print(f"REFRESH_INTERVAL_MINUTES: {os.getenv('REFRESH_INTERVAL_MINUTES', '(not set)')}")
    print(f"HEALTH_PORT: {os.getenv('HEALTH_PORT', '(not set)')}")
    print("-" * 60)
    try:
        from worker import storage
        from worker.config import config

        mode = storage.get_storage_mode()
        print(f"存储模式: {mode}")
        print(f"scheduled_refresh_enabled: {config.retry.scheduled_refresh_enabled}")
        print(f"scheduled_refresh_cron: {config.retry.scheduled_refresh_cron}")
        print(f"scheduled_refresh_interval_minutes(legacy): {config.retry.scheduled_refresh_interval_minutes}")
        print(f"refresh_window_hours: {config.basic.refresh_window_hours}")
        print(f"browser_headless: {config.basic.browser_headless}")
        print(f"auto_register_enabled: {config.retry.auto_register_enabled}")
        print(f"min_account_count: {config.retry.min_account_count}")
    except Exception as exc:
        print(f"配置读取失败: {exc}")


def _test_remote_connection_inner() -> Tuple[bool, str]:
    from worker.remote_project_bridge import RemoteProjectBridge

    bridge = RemoteProjectBridge()
    settings = bridge.get_settings()
    accounts_payload = bridge.get_accounts_config()
    accounts = accounts_payload.get("accounts") if isinstance(accounts_payload, dict) else None
    if not isinstance(accounts, list):
        raise RuntimeError("远程返回的账号格式异常（accounts 不是列表）")
    retry = settings.get("retry", {}) if isinstance(settings, dict) else {}
    basic = settings.get("basic", {}) if isinstance(settings, dict) else {}
    message = (
        f"远程连接成功，账号数={len(accounts)}，"
        f"scheduled_refresh_enabled={retry.get('scheduled_refresh_enabled')}，"
        f"refresh_window_hours={basic.get('refresh_window_hours')}"
    )
    return True, message


def test_remote_connection() -> None:
    _print_header("测试远程连接")
    try:
        ok, message = _test_remote_connection_inner()
        if ok:
            print("结果: 成功")
            print(message)
    except Exception as exc:
        print("结果: 失败")
        print(f"错误: {exc}")


async def run_once_refresh() -> dict:
    from worker.refresh_service import RefreshService

    service = RefreshService()
    summary = await service.run_once(
        trigger="cli-once",
        reload_config=True,
        allow_when_disabled=True,
    )
    return summary


def run_once_command() -> None:
    _print_header("立即刷新一次")
    try:
        summary = asyncio.run(run_once_refresh())
    except KeyboardInterrupt:
        print("已取消。")
        return
    except Exception as exc:
        print(f"执行失败: {exc}")
        return

    print("执行完成。")
    for key in (
        "trigger",
        "skipped",
        "reason",
        "deleted_expired",
        "expiring_count",
        "task_status",
        "success_count",
        "fail_count",
        "auto_register_attempted",
    ):
        print(f"- {key}: {summary.get(key)}")


def run_polling_command() -> None:
    from worker.refresh_service import RefreshService

    _print_header("启动守护轮询（前台）")
    print("按 Ctrl+C 停止。")
    service = RefreshService()

    async def _runner() -> None:
        await service.start_polling()

    try:
        asyncio.run(_runner())
    except KeyboardInterrupt:
        service.stop_polling()
        print("已停止守护轮询。")


def run_env_wizard() -> None:
    _print_header("远程模式配置向导")
    current_url = os.getenv("REMOTE_PROJECT_BASE_URL", "").strip()
    current_pwd = os.getenv("REMOTE_PROJECT_PASSWORD", "").strip()
    current_verify = os.getenv("REMOTE_PROJECT_VERIFY_SSL", "true").strip().lower() or "true"
    current_timeout = os.getenv("REMOTE_PROJECT_TIMEOUT_SECONDS", "30").strip() or "30"
    current_force = os.getenv("FORCE_REFRESH_ENABLED", "true").strip().lower() or "true"
    current_interval = os.getenv("REFRESH_INTERVAL_MINUTES", "30").strip() or "30"

    print("直接回车可保留当前值。")
    base_url = input(f"REMOTE_PROJECT_BASE_URL [{current_url}]: ").strip() or current_url
    password_input = input(
        f"REMOTE_PROJECT_PASSWORD [{_mask_secret(current_pwd)}] (输入新值覆盖，回车保留): "
    ).strip()
    password = password_input if password_input else current_pwd
    verify_ssl = input(f"REMOTE_PROJECT_VERIFY_SSL [{current_verify}]: ").strip() or current_verify
    timeout = input(f"REMOTE_PROJECT_TIMEOUT_SECONDS [{current_timeout}]: ").strip() or current_timeout
    force_enabled = input(f"FORCE_REFRESH_ENABLED [{current_force}]: ").strip() or current_force
    interval = input(f"REFRESH_INTERVAL_MINUTES [{current_interval}]: ").strip() or current_interval

    if not base_url:
        print("未填写 REMOTE_PROJECT_BASE_URL，已取消。")
        return
    if not password:
        print("未填写 REMOTE_PROJECT_PASSWORD，已取消。")
        return

    updates = {
        "REMOTE_PROJECT_BASE_URL": base_url,
        "REMOTE_PROJECT_PASSWORD": password,
        "REMOTE_PROJECT_VERIFY_SSL": verify_ssl,
        "REMOTE_PROJECT_TIMEOUT_SECONDS": timeout,
        "FORCE_REFRESH_ENABLED": force_enabled,
        "REFRESH_INTERVAL_MINUTES": interval,
    }

    path = _save_env_updates(updates)
    load_dotenv(path, override=True)
    print(f"已写入: {path.resolve()}")


def interactive_menu() -> None:
    while True:
        _print_header("refresh-worker 中文交互菜单")
        print("1. 查看当前配置")
        print("2. 测试远程连接")
        print("3. 立即刷新一次")
        print("4. 启动守护轮询（前台）")
        print("5. 远程模式配置向导（写入 .env）")
        print("0. 退出")
        choice = input("\n请选择: ").strip()

        if choice == "1":
            show_current_config()
            input("\n按回车继续...")
        elif choice == "2":
            test_remote_connection()
            input("\n按回车继续...")
        elif choice == "3":
            run_once_command()
            input("\n按回车继续...")
        elif choice == "4":
            run_polling_command()
            input("\n按回车继续...")
        elif choice == "5":
            run_env_wizard()
            input("\n按回车继续...")
        elif choice == "0":
            print("已退出。")
            return
        else:
            print("无效选项，请重试。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="gemini-refresh-worker CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("menu", help="启动中文交互菜单")
    sub.add_parser("once", help="立即执行一次刷新")
    sub.add_parser("poll", help="启动守护轮询（前台）")
    sub.add_parser("doctor", help="测试远程连接并打印配置")
    sub.add_parser("wizard", help="远程模式配置向导（写入 .env）")
    return parser


def main() -> None:
    _setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    cmd = args.command or "menu"
    if cmd == "menu":
        interactive_menu()
    elif cmd == "once":
        run_once_command()
    elif cmd == "poll":
        run_polling_command()
    elif cmd == "doctor":
        show_current_config()
        test_remote_connection()
    elif cmd == "wizard":
        run_env_wizard()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
