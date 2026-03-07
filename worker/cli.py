"""
Interactive CLI for gemini-refresh-worker.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

LANG_ZH = "zh"
LANG_EN = "en"
CLI_LANG_ENV_KEY = "CLI_LANG"
DEFAULT_BROWSER_MODE = "normal"
VALID_BROWSER_MODES = {"normal", "silent", "headless"}
DEFAULT_LANG = LANG_ZH
CURRENT_LANG = DEFAULT_LANG


def _normalize_lang(value: str) -> str:
    raw = (value or "").strip().lower()
    if raw in {LANG_EN, "english"}:
        return LANG_EN
    if raw in {LANG_ZH, "cn", "zh-cn", "chinese", "中文"}:
        return LANG_ZH
    return DEFAULT_LANG


def _language_label(lang: str = "") -> str:
    target = _normalize_lang(lang or CURRENT_LANG)
    return "中文" if target == LANG_ZH else "English"


def _t(zh: str, en: str) -> str:
    return zh if CURRENT_LANG == LANG_ZH else en


def _is_yes(value: str) -> bool:
    return (value or "").strip().lower() in {"y", "yes", "1", "true", "是"}


def _normalize_browser_mode(value: str, default: str = DEFAULT_BROWSER_MODE) -> str:
    raw = (value or "").strip().lower()
    if raw in VALID_BROWSER_MODES:
        return raw
    return default


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


def _set_cli_language(lang: str, persist: bool = False) -> None:
    global CURRENT_LANG
    normalized = _normalize_lang(lang)
    CURRENT_LANG = normalized
    os.environ[CLI_LANG_ENV_KEY] = normalized
    if persist:
        path = _save_env_updates({CLI_LANG_ENV_KEY: normalized})
        load_dotenv(path, override=True)
        print(
            f"{_t('已写入语言配置', 'Saved language setting')}: "
            f"{path.resolve()} ({CLI_LANG_ENV_KEY}={normalized})"
        )


def _print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def _print_config_item(key: str, value: object, zh_desc: str, en_desc: str) -> None:
    print(f"{key} ({_t(zh_desc, en_desc)}): {value}")


def show_current_config() -> None:
    _print_header(_t("当前配置概览", "Current Configuration"))

    db_url = os.getenv("DATABASE_URL", "").strip()
    _print_config_item(
        "DATABASE_URL",
        _t("已设置" if db_url else "未设置", "set" if db_url else "not set"),
        "数据库连接字符串（直连模式）",
        "database URL (direct mode)",
    )
    _print_config_item(
        "REMOTE_PROJECT_BASE_URL",
        os.getenv("REMOTE_PROJECT_BASE_URL", "").strip() or "(not set)",
        "远程项目地址",
        "remote project base URL",
    )
    _print_config_item(
        "REMOTE_PROJECT_PASSWORD",
        _mask_secret(os.getenv("REMOTE_PROJECT_PASSWORD", "").strip()),
        "远程登录密码 / ADMIN_KEY",
        "remote login password / ADMIN_KEY",
    )
    _print_config_item(
        "FORCE_REFRESH_ENABLED",
        os.getenv("FORCE_REFRESH_ENABLED", "(not set)"),
        "强制启用/禁用定时刷新",
        "force enable/disable scheduled refresh",
    )
    _print_config_item(
        "REFRESH_INTERVAL_MINUTES",
        os.getenv("REFRESH_INTERVAL_MINUTES", "(not set)"),
        "刷新检测间隔（分钟）",
        "refresh interval in minutes",
    )
    _print_config_item(
        "BROWSER_MODE",
        _normalize_browser_mode(os.getenv("BROWSER_MODE", ""), "(not set)"),
        "浏览器模式（normal / silent / headless）",
        "browser mode (normal / silent / headless)",
    )
    _print_config_item(
        "BROWSER_HEADLESS",
        os.getenv("BROWSER_HEADLESS", "(not set)"),
        "兼容旧字段：是否无头（被 BROWSER_MODE 覆盖）",
        "legacy headless flag (overridden by BROWSER_MODE)",
    )
    _print_config_item(
        "PROXY_FOR_AUTH",
        os.getenv("PROXY_FOR_AUTH", "(not set)"),
        "本机认证代理",
        "local proxy for auth",
    )
    _print_config_item(
        "REMOTE_PROJECT_USE_REMOTE_PROXY_FOR_AUTH",
        os.getenv("REMOTE_PROJECT_USE_REMOTE_PROXY_FOR_AUTH", "(not set)"),
        "是否继承远程 proxy_for_auth",
        "inherit remote proxy_for_auth or not",
    )
    _print_config_item(
        "HEALTH_PORT",
        os.getenv("HEALTH_PORT", "(not set)"),
        "健康检查端口",
        "health check port",
    )
    _print_config_item(
        CLI_LANG_ENV_KEY,
        CURRENT_LANG,
        "CLI 交互语言（zh/en）",
        "CLI language (zh/en)",
    )

    print("-" * 60)
    try:
        from worker import storage
        from worker.config import config

        mode = storage.get_storage_mode()
        _print_config_item("storage_mode", mode, "当前存储模式", "current storage mode")
        _print_config_item(
            "scheduled_refresh_enabled",
            config.retry.scheduled_refresh_enabled,
            "是否启用定时刷新",
            "scheduled refresh enabled",
        )
        _print_config_item(
            "scheduled_refresh_cron",
            config.retry.scheduled_refresh_cron,
            "cron 表达式（若配置）",
            "scheduled cron expression",
        )
        _print_config_item(
            "scheduled_refresh_interval_minutes(legacy)",
            config.retry.scheduled_refresh_interval_minutes,
            "旧版轮询间隔（分钟）",
            "legacy interval in minutes",
        )
        _print_config_item(
            "refresh_window_hours",
            config.basic.refresh_window_hours,
            "刷新窗口（小时）",
            "refresh window in hours",
        )
        _print_config_item(
            "browser_mode",
            config.basic.browser_mode,
            "浏览器模式",
            "browser mode",
        )
        _print_config_item(
            "browser_headless",
            config.basic.browser_headless,
            "运行时是否无头（兼容显示）",
            "runtime headless flag (compat)",
        )
        _print_config_item(
            "proxy_for_auth(runtime)",
            config.basic.proxy_for_auth or "(empty)",
            "运行时认证代理",
            "runtime auth proxy",
        )
        _print_config_item(
            "auto_register_enabled",
            config.retry.auto_register_enabled,
            "自动注册开关",
            "auto register enabled",
        )
        _print_config_item(
            "min_account_count",
            config.retry.min_account_count,
            "最小活跃账号阈值",
            "minimum active account threshold",
        )
    except Exception as exc:
        print(f"{_t('配置读取失败', 'Failed to read configuration')}: {exc}")


def _test_remote_connection_inner() -> Tuple[bool, str]:
    from worker.remote_project_bridge import RemoteProjectBridge

    bridge = RemoteProjectBridge()
    settings = bridge.get_settings()
    accounts_payload = bridge.get_accounts_config()
    accounts = accounts_payload.get("accounts") if isinstance(accounts_payload, dict) else None
    if not isinstance(accounts, list):
        raise RuntimeError(
            _t(
                "远程返回账号格式异常（accounts 不是列表）",
                "Invalid remote account payload (accounts is not a list)",
            )
        )

    retry = settings.get("retry", {}) if isinstance(settings, dict) else {}
    basic = settings.get("basic", {}) if isinstance(settings, dict) else {}
    message = (
        f"{_t('远程连接成功', 'Remote connection successful')}, "
        f"{_t('账号数', 'accounts')}={len(accounts)}, "
        f"scheduled_refresh_enabled={retry.get('scheduled_refresh_enabled')}, "
        f"refresh_window_hours={basic.get('refresh_window_hours')}"
    )
    return True, message


def test_remote_connection() -> None:
    _print_header(_t("测试远程连接", "Test Remote Connection"))
    try:
        ok, message = _test_remote_connection_inner()
        if ok:
            print(f"{_t('结果', 'Result')}: {_t('成功', 'Success')}")
            print(message)
    except Exception as exc:
        print(f"{_t('结果', 'Result')}: {_t('失败', 'Failed')}")
        print(f"{_t('错误', 'Error')}: {exc}")


def _probe_http(url: str, proxy: str = "", timeout: int = 12) -> Tuple[bool, str]:
    proxies = None
    if proxy:
        proxies = {"http": proxy, "https": proxy}
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=False, proxies=proxies)
        return True, f"HTTP {resp.status_code}"
    except Exception as exc:
        return False, str(exc)


def diagnose_google_access() -> None:
    from worker import storage
    from worker.config import config
    from worker.proxy_utils import parse_proxy_setting

    _print_header(_t("Google 连通性与代理诊断", "Google Connectivity & Proxy Diagnostics"))

    storage_mode = storage.get_storage_mode()
    raw_proxy = config.basic.proxy_for_auth or ""
    proxy_url, no_proxy = parse_proxy_setting(raw_proxy)
    env_proxy = os.getenv("PROXY_FOR_AUTH")

    print(f"storage_mode: {storage_mode}")
    print(f"proxy_for_auth(runtime): {proxy_url or '(empty)'}")
    print(f"no_proxy: {no_proxy or '(empty)'}")
    print(f"PROXY_FOR_AUTH env: {env_proxy if env_proxy is not None else '(not set)'}")
    print("-" * 60)

    urls = [
        "https://www.google.com/",
        "https://auth.business.gemini.google/",
        "https://business.gemini.google/",
    ]

    print(_t("直连检查:", "Direct connection check:"))
    for url in urls:
        ok, detail = _probe_http(url, proxy="")
        print(f"- {url} -> {'OK' if ok else 'FAIL'} ({detail})")

    if proxy_url:
        print("\n" + _t("代理检查:", "Proxy check:"))
        for url in urls:
            ok, detail = _probe_http(url, proxy=proxy_url)
            print(f"- {url} -> {'OK' if ok else 'FAIL'} ({detail})")
    else:
        print(
            "\n"
            + _t(
                "代理检查: 跳过（当前未启用 PROXY_FOR_AUTH）",
                "Proxy check: skipped (PROXY_FOR_AUTH is not enabled)",
            )
        )

    if storage_mode == "remote" and env_proxy is None:
        print("\n" + _t("提示:", "Tip:"))
        print(
            "- "
            + _t(
                "远程模式默认不继承远程站点的 proxy_for_auth，避免把远程 localhost 代理误用到本机。",
                "Remote mode does not inherit remote proxy_for_auth by default to avoid misusing remote localhost proxies.",
            )
        )
        print(
            "- "
            + _t(
                "如果本机访问 Google 需要代理，请在本地 .env 设置 PROXY_FOR_AUTH（例如 socks5h://127.0.0.1:7890）。",
                "If your local machine needs a proxy to access Google, set PROXY_FOR_AUTH in local .env (e.g. socks5h://127.0.0.1:7890).",
            )
        )


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
    _print_header(_t("立即刷新一次", "Run One Refresh Now"))
    try:
        summary = asyncio.run(run_once_refresh())
    except KeyboardInterrupt:
        print(_t("已取消。", "Cancelled."))
        return
    except Exception as exc:
        print(f"{_t('执行失败', 'Run failed')}: {exc}")
        return

    print(_t("执行完成。", "Completed."))
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

    _print_header(_t("启动守护轮询（前台）", "Start Foreground Polling"))
    print(_t("按 Ctrl+C 停止。", "Press Ctrl+C to stop."))
    service = RefreshService()

    async def _runner() -> None:
        await service.start_polling()

    try:
        asyncio.run(_runner())
    except KeyboardInterrupt:
        service.stop_polling()
        print(_t("已停止守护轮询。", "Polling stopped."))


def run_env_wizard() -> None:
    _print_header(_t("远程模式配置向导", "Remote Mode Setup Wizard"))
    current_url = os.getenv("REMOTE_PROJECT_BASE_URL", "").strip()
    current_pwd = os.getenv("REMOTE_PROJECT_PASSWORD", "").strip()
    current_verify = os.getenv("REMOTE_PROJECT_VERIFY_SSL", "true").strip().lower() or "true"
    current_timeout = os.getenv("REMOTE_PROJECT_TIMEOUT_SECONDS", "30").strip() or "30"
    current_force = os.getenv("FORCE_REFRESH_ENABLED", "true").strip().lower() or "true"
    current_interval = os.getenv("REFRESH_INTERVAL_MINUTES", "30").strip() or "30"
    current_browser_mode = _normalize_browser_mode(os.getenv("BROWSER_MODE", DEFAULT_BROWSER_MODE), DEFAULT_BROWSER_MODE)
    current_proxy = os.getenv("PROXY_FOR_AUTH", "").strip()
    current_use_remote_proxy = os.getenv("REMOTE_PROJECT_USE_REMOTE_PROXY_FOR_AUTH", "false").strip().lower() or "false"
    current_lang = _normalize_lang(os.getenv(CLI_LANG_ENV_KEY, CURRENT_LANG))

    print(_t("直接回车可保留当前值。", "Press Enter to keep current values."))
    base_url = input(
        f"REMOTE_PROJECT_BASE_URL [{current_url}] "
        f"({_t('远程项目地址', 'remote project URL')}): "
    ).strip() or current_url
    password_input = input(
        f"REMOTE_PROJECT_PASSWORD [{_mask_secret(current_pwd)}] "
        f"({_t('输入新值覆盖，回车保留', 'type new value to override, press Enter to keep')}): "
    ).strip()
    password = password_input if password_input else current_pwd
    verify_ssl = input(
        f"REMOTE_PROJECT_VERIFY_SSL [{current_verify}] "
        f"({_t('是否校验 SSL', 'verify SSL or not')}): "
    ).strip() or current_verify
    timeout = input(
        f"REMOTE_PROJECT_TIMEOUT_SECONDS [{current_timeout}] "
        f"({_t('远程请求超时秒数', 'remote request timeout seconds')}): "
    ).strip() or current_timeout
    force_enabled = input(
        f"FORCE_REFRESH_ENABLED [{current_force}] "
        f"({_t('是否强制启用定时刷新', 'force scheduled refresh on/off')}): "
    ).strip() or current_force
    interval = input(
        f"REFRESH_INTERVAL_MINUTES [{current_interval}] "
        f"({_t('刷新间隔分钟', 'refresh interval in minutes')}): "
    ).strip() or current_interval
    browser_mode = _normalize_browser_mode(
        input(
            f"BROWSER_MODE [{current_browser_mode}] "
            f"({_t('浏览器模式：normal/silent/headless', 'browser mode: normal/silent/headless')}): "
        ).strip()
        or current_browser_mode,
        current_browser_mode,
    )
    proxy_for_auth = input(
        f"PROXY_FOR_AUTH [{current_proxy}] "
        f"({_t('本机代理，可留空', 'local proxy, optional')}): "
    ).strip() or current_proxy
    use_remote_proxy = input(
        f"REMOTE_PROJECT_USE_REMOTE_PROXY_FOR_AUTH [{current_use_remote_proxy}] "
        f"({_t('是否继承远程代理，默认false', 'inherit remote proxy, default false')}): "
    ).strip() or current_use_remote_proxy
    cli_lang = _normalize_lang(
        input(
            f"{CLI_LANG_ENV_KEY} [{current_lang}] "
            f"({_t('交互语言：zh/en', 'CLI language: zh/en')}): "
        ).strip()
        or current_lang
    )

    if not base_url:
        print(_t("未填写 REMOTE_PROJECT_BASE_URL，已取消。", "REMOTE_PROJECT_BASE_URL is required, cancelled."))
        return
    if not password:
        print(_t("未填写 REMOTE_PROJECT_PASSWORD，已取消。", "REMOTE_PROJECT_PASSWORD is required, cancelled."))
        return

    updates = {
        "REMOTE_PROJECT_BASE_URL": base_url,
        "REMOTE_PROJECT_PASSWORD": password,
        "REMOTE_PROJECT_VERIFY_SSL": verify_ssl,
        "REMOTE_PROJECT_TIMEOUT_SECONDS": timeout,
        "FORCE_REFRESH_ENABLED": force_enabled,
        "REFRESH_INTERVAL_MINUTES": interval,
        "BROWSER_MODE": browser_mode,
        "PROXY_FOR_AUTH": proxy_for_auth,
        "REMOTE_PROJECT_USE_REMOTE_PROXY_FOR_AUTH": use_remote_proxy,
        CLI_LANG_ENV_KEY: cli_lang,
    }

    path = _save_env_updates(updates)
    load_dotenv(path, override=True)
    _set_cli_language(cli_lang, persist=False)
    print(f"{_t('已写入', 'Written to')}: {path.resolve()}")


def switch_language_interactive() -> None:
    _print_header(_t("语言切换", "Language Switch"))
    print("1. 中文")
    print("2. English")
    print(f"0. {_t('取消', 'Cancel')}")

    choice = input(f"\n{_t('请选择', 'Choose')}: ").strip()
    if choice == "0":
        print(_t("已取消。", "Cancelled."))
        return

    mapping = {"1": LANG_ZH, "2": LANG_EN}
    if choice not in mapping:
        print(_t("无效选项，已取消。", "Invalid option, cancelled."))
        return

    selected = mapping[choice]
    _set_cli_language(selected, persist=False)
    print(f"{_t('当前语言', 'Current language')}: {_language_label()}")

    persist = input(
        _t("是否写入 .env 作为默认语言？(y/N): ", "Save to .env as default language? (y/N): ")
    ).strip()
    if _is_yes(persist):
        _set_cli_language(selected, persist=True)


def interactive_menu() -> None:
    while True:
        _print_header(_t("刷新 Worker 控制台", "Refresh Worker Console"))
        print(f"1. {_t('查看当前配置（含中文解释）', 'Show current configuration')}")
        print(f"2. {_t('测试远程连接', 'Test remote connection')}")
        print(f"3. {_t('Google 连通性与代理诊断', 'Google connectivity and proxy diagnostics')}")
        print(f"4. {_t('立即刷新一次', 'Run one refresh now')}")
        print(f"5. {_t('启动守护轮询（前台）', 'Start foreground polling')}")
        print(f"6. {_t('远程模式配置向导（写入 .env）', 'Remote mode setup wizard (write .env)')}")
        print(f"7. {_t('切换语言', 'Switch language')} ({_t('当前', 'current')}: {_language_label()})")
        print(f"0. {_t('退出', 'Exit')}")
        choice = input(f"\n{_t('请选择', 'Choose')}: ").strip()

        if choice == "1":
            show_current_config()
            input(f"\n{_t('按回车继续...', 'Press Enter to continue...')}")
        elif choice == "2":
            test_remote_connection()
            input(f"\n{_t('按回车继续...', 'Press Enter to continue...')}")
        elif choice == "3":
            diagnose_google_access()
            input(f"\n{_t('按回车继续...', 'Press Enter to continue...')}")
        elif choice == "4":
            run_once_command()
            input(f"\n{_t('按回车继续...', 'Press Enter to continue...')}")
        elif choice == "5":
            run_polling_command()
            input(f"\n{_t('按回车继续...', 'Press Enter to continue...')}")
        elif choice == "6":
            run_env_wizard()
            input(f"\n{_t('按回车继续...', 'Press Enter to continue...')}")
        elif choice == "7":
            switch_language_interactive()
            input(f"\n{_t('按回车继续...', 'Press Enter to continue...')}")
        elif choice == "0":
            print(_t("已退出。", "Exited."))
            return
        else:
            print(_t("无效选项，请重试。", "Invalid option, please try again."))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=_t("gemini-refresh-worker 命令行工具", "gemini-refresh-worker CLI"))
    parser.add_argument(
        "--lang",
        choices=[LANG_ZH, LANG_EN],
        help=_t("界面语言（默认中文）", "CLI language (default: zh)"),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("menu", help=_t("启动交互菜单", "Start interactive menu"))
    sub.add_parser("once", help=_t("立即执行一次刷新", "Run one refresh immediately"))
    sub.add_parser("poll", help=_t("启动守护轮询（前台）", "Start foreground polling"))
    sub.add_parser("doctor", help=_t("打印配置 + 远程连接 + Google诊断", "Print config + remote check + Google diagnostics"))
    sub.add_parser("wizard", help=_t("远程模式配置向导（写入 .env）", "Remote mode setup wizard (write .env)"))
    sub.add_parser("google", help=_t("仅执行 Google 连通性与代理诊断", "Run only Google connectivity and proxy diagnostics"))

    lang_parser = sub.add_parser("lang", help=_t("切换 CLI 语言", "Switch CLI language"))
    lang_parser.add_argument("value", nargs="?", choices=[LANG_ZH, LANG_EN], help=_t("目标语言：zh/en", "target language: zh/en"))
    lang_parser.add_argument("--save", action="store_true", help=_t("写入 .env", "persist to .env"))

    return parser


def main() -> None:
    global CURRENT_LANG
    CURRENT_LANG = _normalize_lang(os.getenv(CLI_LANG_ENV_KEY, DEFAULT_LANG))

    _setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    if args.lang:
        _set_cli_language(args.lang, persist=False)

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
        diagnose_google_access()
    elif cmd == "wizard":
        run_env_wizard()
    elif cmd == "google":
        diagnose_google_access()
    elif cmd == "lang":
        target = args.value or (LANG_EN if CURRENT_LANG == LANG_ZH else LANG_ZH)
        _set_cli_language(target, persist=args.save)
        print(f"{_t('当前语言', 'Current language')}: {_language_label()}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
