"""
Refresh service — core polling loop, expiry detection, and single-account refresh.

Simplified from core/login_service.py + core/base_task_service.py.
Does NOT depend on MultiAccountManager or FastAPI.
"""

import asyncio
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from worker import storage
from worker.config import config, config_manager
from worker.proxy_utils import parse_proxy_setting

logger = logging.getLogger("gemini.refresh")

# Check interval when scheduled refresh is disabled
CONFIG_CHECK_INTERVAL_SECONDS = 60


# ==================== Task framework (simplified) ====================

class TaskCancelledError(Exception):
    """Used to interrupt task execution from threads/callbacks."""


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RefreshTask:
    """Refresh task data class."""
    id: str
    account_ids: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    success_count: int = 0
    fail_count: int = 0
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    logs: List[Dict[str, str]] = field(default_factory=list)
    cancel_requested: bool = False
    cancel_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": "login",
            "status": self.status.value,
            "progress": self.progress,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "results": self.results,
            "error": self.error,
            "logs": self.logs,
            "cancel_requested": self.cancel_requested,
            "cancel_reason": self.cancel_reason,
            "account_ids": self.account_ids,
        }


# ==================== Refresh Service ====================

class RefreshService:
    """
    Standalone refresh service.

    Polls the database for accounts nearing expiry and refreshes
    their credentials via browser automation.
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._is_polling = False
        self._current_task: Optional[RefreshTask] = None
        self._round_lock = asyncio.Lock()
        self._log_lock = threading.Lock()
        self._cancel_hooks: Dict[str, List[Callable[[], None]]] = {}
        self._cancel_hooks_lock = threading.Lock()
        self._refresh_timestamps: Dict[str, float] = {}
        self._triggered_today: set = set()

    # ---- logging helpers ----

    def _append_log(self, task: RefreshTask, level: str, message: str) -> None:
        entry = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "level": level,
            "message": message,
        }
        with self._log_lock:
            task.logs.append(entry)
            if len(task.logs) > 200:
                task.logs = task.logs[-200:]

        log_message = f"[REFRESH] {message}"
        if level == "warning":
            logger.warning(log_message)
        elif level == "error":
            logger.error(log_message)
        else:
            logger.info(log_message)

        # Cooperative cancellation
        if task.cancel_requested:
            safe_messages = (
                "cancel requested:",
                "task cancelled",
                "task cancelled while pending",
                "login task cancelled:",
            )
            if not any(message.startswith(x) for x in safe_messages):
                raise TaskCancelledError(task.cancel_reason or "cancelled")

    # ---- cancel hooks ----

    def _add_cancel_hook(self, task_id: str, hook: Callable[[], None]) -> None:
        with self._cancel_hooks_lock:
            self._cancel_hooks.setdefault(task_id, []).append(hook)

    def _fire_cancel_hooks(self, task_id: str) -> None:
        with self._cancel_hooks_lock:
            hooks = list(self._cancel_hooks.get(task_id) or [])
        for hook in hooks:
            try:
                hook()
            except Exception as exc:
                logger.warning("[REFRESH] cancel hook error: %s", str(exc)[:120])

    def _clear_cancel_hooks(self, task_id: str) -> None:
        with self._cancel_hooks_lock:
            self._cancel_hooks.pop(task_id, None)

    # ---- task history ----

    def _save_task_history(self, task: RefreshTask) -> None:
        try:
            storage.save_task_history_entry_sync(task.to_dict())
        except Exception:
            pass

    # ---- accounts loading ----

    @staticmethod
    def _load_accounts() -> list:
        """Load accounts from database."""
        if storage.is_database_enabled():
            data = storage.load_accounts_sync()
            if data is None:
                logger.error("[REFRESH] Database connection failed")
                return []
            return data
        return []

    # ---- expired account deletion ----

    def _get_expired_account_ids(self) -> List[str]:
        """Get list of account IDs whose trial has ended (trial_end expired)."""
        accounts = self._load_accounts()
        expired = []
        beijing_tz = timezone(timedelta(hours=8))
        now = datetime.now(beijing_tz)

        for account in accounts:
            account_id = account.get("id")
            if not account_id:
                continue
            if account.get("disabled"):
                continue

            trial_end = account.get("trial_end")
            if not trial_end:
                continue

            try:
                # trial_end format: "2026-03-25"
                end_date = datetime.strptime(trial_end, "%Y-%m-%d").date()
                today = now.date()
            except Exception:
                continue

            # Trial has ended
            if end_date < today:
                expired.append(account_id)

        return expired

    def _delete_expired_accounts(self) -> int:
        """Delete expired accounts from database. Returns count deleted."""
        expired_ids = self._get_expired_account_ids()
        if not expired_ids:
            return 0

        logger.info(f"[REFRESH] found {len(expired_ids)} expired accounts to delete: {expired_ids}")
        deleted = storage.delete_accounts_sync(expired_ids)
        if deleted > 0:
            logger.info(f"[REFRESH] deleted {deleted} expired accounts")
            # Clean up refresh timestamps for deleted accounts
            for aid in expired_ids:
                self._refresh_timestamps.pop(aid, None)
        return deleted

    # ---- auto registration ----

    def _auto_register_if_needed(self) -> None:
        """Check active account count and register new accounts if below minimum."""
        min_count = config.retry.min_account_count
        if min_count <= 0:
            return

        active_count = storage.count_active_accounts_sync()
        if active_count >= min_count:
            logger.info(f"[REFRESH] active accounts ({active_count}) >= minimum ({min_count}), no registration needed")
            return

        need = min_count - active_count
        logger.info(f"[REFRESH] active accounts ({active_count}) < minimum ({min_count}), registering {need} new accounts")

        # Lazy import to avoid circular dependency
        from worker.register_service import register_one

        for i in range(need):
            logger.info(f"[REGISTER] registering account {i + 1}/{need}...")
            try:
                result = register_one()
            except Exception as exc:
                logger.error(f"[REGISTER] account {i + 1}/{need} failed with exception: {exc}")
                result = {"success": False, "error": str(exc)}

            if result.get("success"):
                email = result.get("email", "unknown")
                logger.info(f"[REGISTER] account {i + 1}/{need} registered successfully: {email}")
            else:
                error = result.get("error", "unknown error")
                logger.error(f"[REGISTER] account {i + 1}/{need} failed: {error}")

            # Wait between registrations to avoid rate limiting
            if i < need - 1:
                logger.info("[REGISTER] waiting 10 seconds before next registration...")
                time.sleep(10)

    # ---- expiry detection ----

    def _get_expiring_accounts(self) -> List[str]:
        """Get list of account IDs nearing expiry."""
        accounts = self._load_accounts()
        expiring = []
        beijing_tz = timezone(timedelta(hours=8))
        now = datetime.now(beijing_tz)

        for account in accounts:
            account_id = account.get("id")
            if not account_id:
                continue

            if account.get("disabled"):
                continue

            mail_provider = (account.get("mail_provider") or "").lower()
            if not mail_provider:
                if account.get("mail_client_id") or account.get("mail_refresh_token"):
                    mail_provider = "microsoft"
                else:
                    mail_provider = "duckmail"

            mail_password = account.get("mail_password") or account.get("email_password")
            if mail_provider == "microsoft":
                if not account.get("mail_client_id") or not account.get("mail_refresh_token"):
                    continue
            elif mail_provider in ("duckmail", "moemail"):
                if not mail_password:
                    continue
            elif mail_provider == "freemail":
                if not config.basic.freemail_jwt_token:
                    continue
            elif mail_provider == "gptmail":
                pass
            else:
                continue

            expires_at = account.get("expires_at")
            if not expires_at:
                continue

            try:
                expire_time = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
                expire_time = expire_time.replace(tzinfo=beijing_tz)
                remaining = (expire_time - now).total_seconds() / 3600
            except Exception:
                continue

            if remaining > config.basic.refresh_window_hours:
                continue

            # Cooldown check: skip recently refreshed accounts
            cooldown_seconds = config.retry.refresh_cooldown_hours * 3600
            if account_id in self._refresh_timestamps:
                elapsed = time.time() - self._refresh_timestamps[account_id]
                if elapsed < cooldown_seconds:
                    logger.debug(f"[REFRESH] skip {account_id}: refreshed {elapsed/3600:.1f}h ago, cooldown {config.retry.refresh_cooldown_hours}h")
                    continue

            expiring.append(account_id)

        return expiring

    # ---- single account refresh ----

    def _refresh_one(self, account_id: str, task: RefreshTask) -> dict:
        """Refresh a single account's credentials."""
        accounts = self._load_accounts()
        account = next((acc for acc in accounts if acc.get("id") == account_id), None)
        if not account:
            return {"success": False, "email": account_id, "error": "account not found"}

        if account.get("disabled"):
            return {"success": False, "email": account_id, "error": "account disabled"}

        # Determine mail provider
        mail_provider = (account.get("mail_provider") or "").lower()
        if not mail_provider:
            if account.get("mail_client_id") or account.get("mail_refresh_token"):
                mail_provider = "microsoft"
            else:
                mail_provider = "duckmail"

        mail_password = account.get("mail_password") or account.get("email_password")
        mail_client_id = account.get("mail_client_id")
        mail_refresh_token = account.get("mail_refresh_token")
        mail_tenant = account.get("mail_tenant") or "consumers"
        proxy_for_auth, _ = parse_proxy_setting(config.basic.proxy_for_auth)

        def log_cb(level, message):
            self._append_log(task, level, f"[{account_id}] {message}")

        log_cb("info", f"📧 邮件提供商: {mail_provider}")

        # Create mail client
        if mail_provider == "microsoft":
            if not mail_client_id or not mail_refresh_token:
                return {"success": False, "email": account_id, "error": "Microsoft OAuth config missing"}
            from worker.mail_clients.microsoft_mail_client import MicrosoftMailClient
            mail_address = account.get("mail_address") or account_id
            client = MicrosoftMailClient(
                client_id=mail_client_id,
                refresh_token=mail_refresh_token,
                tenant=mail_tenant,
                proxy=proxy_for_auth,
                log_callback=log_cb,
            )
            client.set_credentials(mail_address)
        elif mail_provider in ("duckmail", "moemail", "freemail", "gptmail"):
            if mail_provider not in ("freemail", "gptmail") and not mail_password:
                error_message = "邮箱密码缺失" if mail_provider == "duckmail" else "mail password (email_id) missing"
                return {"success": False, "email": account_id, "error": error_message}
            if mail_provider == "freemail" and not account.get("mail_jwt_token") and not config.basic.freemail_jwt_token:
                return {"success": False, "email": account_id, "error": "Freemail JWT Token not configured"}

            mail_address = account.get("mail_address") or account_id

            account_config = {}
            if account.get("mail_base_url"):
                account_config["base_url"] = account["mail_base_url"]
            if account.get("mail_api_key"):
                account_config["api_key"] = account["mail_api_key"]
            if account.get("mail_jwt_token"):
                account_config["jwt_token"] = account["mail_jwt_token"]
            if account.get("mail_verify_ssl") is not None:
                account_config["verify_ssl"] = account["mail_verify_ssl"]
            if account.get("mail_domain"):
                account_config["domain"] = account["mail_domain"]

            from worker.mail_clients import create_temp_mail_client
            client = create_temp_mail_client(
                mail_provider,
                log_cb=log_cb,
                **account_config,
            )
            client.set_credentials(mail_address, mail_password)
            if mail_provider == "moemail":
                client.email_id = mail_password
        else:
            return {"success": False, "email": account_id, "error": f"unsupported mail provider: {mail_provider}"}

        browser_mode = (config.basic.browser_mode or "normal").strip().lower()
        headless = config.basic.browser_headless

        log_cb("info", f"🌐 启动浏览器 (模式={browser_mode}, 无头={headless})...")

        from worker.gemini_automation import GeminiAutomation
        automation = GeminiAutomation(
            proxy=proxy_for_auth,
            browser_mode=browser_mode,
            log_callback=log_cb,
        )
        # Allow external cancel to close browser immediately
        self._add_cancel_hook(task.id, lambda: getattr(automation, "stop", lambda: None)())
        try:
            log_cb("info", "🔐 执行 Gemini 自动登录...")
            result = automation.login_and_extract(account_id, client)
        except Exception as exc:
            log_cb("error", f"❌ 自动登录异常: {exc}")
            return {"success": False, "email": account_id, "error": str(exc)}
        if not result.get("success"):
            error = result.get("error", "自动化流程失败")
            log_cb("error", f"❌ 自动登录失败: {error}")
            return {"success": False, "email": account_id, "error": error}

        log_cb("info", "✅ Gemini 登录成功，正在保存配置...")

        # Update account config
        config_data = result["config"]
        config_data["mail_provider"] = mail_provider
        if mail_provider in ("freemail", "gptmail"):
            config_data["mail_password"] = ""
        else:
            config_data["mail_password"] = mail_password
        if mail_provider == "microsoft":
            config_data["mail_address"] = account.get("mail_address") or account_id
            config_data["mail_client_id"] = mail_client_id
            config_data["mail_refresh_token"] = mail_refresh_token
            config_data["mail_tenant"] = mail_tenant
        config_data["disabled"] = account.get("disabled", False)

        # Preserve account-level mail config fields
        for key in ("mail_base_url", "mail_api_key", "mail_jwt_token", "mail_verify_ssl", "mail_domain", "mail_address"):
            if key in account and key not in config_data:
                config_data[key] = account[key]

        # Update single row in database directly
        merged = dict(account)
        merged.update(config_data)
        storage.update_account_data_sync(account_id, merged)

        log_cb("info", "✅ 配置已保存到数据库")
        return {"success": True, "email": account_id, "config": config_data}

    # ---- task execution ----

    async def _run_refresh_task(self, task: RefreshTask) -> None:
        """Execute a refresh task (iterate accounts)."""
        loop = asyncio.get_running_loop()
        self._append_log(task, "info", f"🚀 刷新任务已启动 (共 {len(task.account_ids)} 个账号)")

        for idx, account_id in enumerate(task.account_ids, 1):
            if task.cancel_requested:
                self._append_log(task, "warning", f"login task cancelled: {task.cancel_reason or 'cancelled'}")
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                return

            try:
                self._append_log(task, "info", f"📊 进度: {idx}/{len(task.account_ids)}")
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self._append_log(task, "info", f"🔄 开始刷新账号: {account_id}")
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                result = await loop.run_in_executor(self._executor, self._refresh_one, account_id, task)
            except TaskCancelledError:
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                return
            except Exception as exc:
                result = {"success": False, "email": account_id, "error": str(exc)}

            task.progress += 1
            task.results.append(result)

            if result.get("success"):
                task.success_count += 1
                self._refresh_timestamps[account_id] = time.time()
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self._append_log(task, "info", f"🎉 刷新成功: {account_id}")
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            else:
                task.fail_count += 1
                error = result.get('error', '未知错误')
                self._append_log(task, "error", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self._append_log(task, "error", f"❌ 刷新失败: {account_id}")
                self._append_log(task, "error", f"❌ 失败原因: {error}")
                self._append_log(task, "error", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

                # 403 域名封禁 → 自动禁用账户
                if '403' in error:
                    try:
                        storage.disable_account_sync(account_id, reason="403 Access Restricted")
                        self._append_log(task, "warning", f"🚫 已自动禁用账户: {account_id} (403 域名封禁)")
                    except Exception as e:
                        logger.warning(f"[REFRESH] 自动禁用失败: {account_id}: {e}")

        if task.cancel_requested:
            task.status = TaskStatus.CANCELLED
        else:
            task.status = TaskStatus.SUCCESS if task.fail_count == 0 else TaskStatus.FAILED
        task.finished_at = time.time()
        self._append_log(task, "info", f"🏁 刷新任务完成 (成功: {task.success_count}, 失败: {task.fail_count}, 总计: {len(task.account_ids)})")

    # ---- run single batch ----

    async def _run_single_batch(self, account_ids: List[str]) -> RefreshTask:
        """Run a single batch of accounts and wait for completion."""
        task = RefreshTask(id=str(uuid.uuid4()), account_ids=account_ids)
        self._current_task = task
        task.status = TaskStatus.RUNNING

        try:
            await self._run_refresh_task(task)
        except asyncio.CancelledError:
            task.cancel_requested = True
            task.status = TaskStatus.CANCELLED
            task.finished_at = time.time()
        except TaskCancelledError:
            task.cancel_requested = True
            task.status = TaskStatus.CANCELLED
            task.finished_at = time.time()
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.finished_at = time.time()
            logger.error("[REFRESH] task error: %s", exc)
        finally:
            self._clear_cancel_hooks(task.id)
            self._save_task_history(task)
            self._current_task = None

        return task

    async def _run_refresh_round(self) -> dict:
        """Run one full refresh round and return a summary."""
        summary = {
            "deleted_expired": 0,
            "expiring_count": 0,
            "task_status": "idle",
            "success_count": 0,
            "fail_count": 0,
            "auto_register_attempted": False,
        }

        if config.retry.delete_expired_accounts:
            try:
                summary["deleted_expired"] = self._delete_expired_accounts()
            except Exception as exc:
                logger.warning("[REFRESH] expired account deletion failed: %s", exc)

        expiring = self._get_expiring_accounts()
        summary["expiring_count"] = len(expiring)
        if not expiring:
            logger.info("[REFRESH] no accounts need refresh this round")
        else:
            logger.info(f"[REFRESH] {len(expiring)} accounts to refresh in one task")
            try:
                task = await self._run_single_batch(expiring)
                summary["task_status"] = task.status.value
                summary["success_count"] = task.success_count
                summary["fail_count"] = task.fail_count
                logger.info(
                    "[REFRESH] refresh round complete (success: %s, fail: %s)",
                    task.success_count,
                    task.fail_count,
                )
            except Exception as exc:
                summary["task_status"] = "error"
                logger.warning("[REFRESH] refresh round error: %s", exc)

        if config.retry.auto_register_enabled:
            summary["auto_register_attempted"] = True
            try:
                self._auto_register_if_needed()
            except Exception as exc:
                logger.warning("[REFRESH] auto registration failed: %s", exc)

        return summary

    async def run_once(self, trigger: str = "manual", reload_config: bool = True, allow_when_disabled: bool = True) -> dict:
        """
        Run exactly one refresh round.

        Returns a summary dict:
          - trigger
          - skipped (bool)
          - reason
          - round fields from _run_refresh_round()
        """
        summary = {
            "trigger": trigger,
            "skipped": False,
            "reason": "",
            "deleted_expired": 0,
            "expiring_count": 0,
            "task_status": "idle",
            "success_count": 0,
            "fail_count": 0,
            "auto_register_attempted": False,
        }

        if reload_config:
            try:
                config_manager.reload()
            except Exception as exc:
                logger.warning("[REFRESH] config reload failed before run_once: %s", exc)

        if not allow_when_disabled and not config.retry.scheduled_refresh_enabled:
            summary["skipped"] = True
            summary["reason"] = "scheduled refresh disabled"
            logger.debug("[REFRESH] run_once skipped because scheduled refresh is disabled")
            return summary

        if self._round_lock.locked():
            summary["skipped"] = True
            summary["reason"] = "refresh round already running"
            logger.warning("[REFRESH] run_once skipped: another round is already running")
            return summary

        async with self._round_lock:
            round_summary = await self._run_refresh_round()
            summary.update(round_summary)
            return summary

    # ---- cron scheduling ----

    @staticmethod
    def _parse_cron(cron_str: str) -> dict:
        """Parse cron expression.
        Supports:
          - '08:00,20:00' -> {'mode': 'daily', 'times': ['08:00', '20:00']}
          - '*/120'       -> {'mode': 'interval', 'minutes': 120}
        """
        cron_str = cron_str.strip()
        if cron_str.startswith("*/"):
            try:
                minutes = int(cron_str[2:])
                return {"mode": "interval", "minutes": max(minutes, 5)}
            except ValueError:
                return {"mode": "interval", "minutes": 120}
        else:
            times = [t.strip() for t in cron_str.split(",") if t.strip()]
            valid = []
            for t in times:
                parts = t.split(":")
                if len(parts) == 2:
                    try:
                        h, m = int(parts[0]), int(parts[1])
                        if 0 <= h <= 23 and 0 <= m <= 59:
                            valid.append(f"{h:02d}:{m:02d}")
                    except ValueError:
                        pass
            return {"mode": "daily", "times": valid or ["08:00", "20:00"]}

    async def _wait_for_next_trigger(self) -> None:
        """Wait for next trigger time.
        - interval mode: wait N minutes
        - daily mode: wait until next matching HH:MM, each time only triggers once per day
        """
        cron_str = config.retry.scheduled_refresh_cron
        # Backward compat: if old field has value and new field is default, convert to interval
        if (not cron_str or cron_str == "08:00,20:00") and config.retry.scheduled_refresh_interval_minutes > 0:
            cron_str = f"*/{config.retry.scheduled_refresh_interval_minutes}"

        cron = self._parse_cron(cron_str)

        if cron["mode"] == "interval":
            minutes = cron["minutes"]
            logger.info(f"[REFRESH] interval mode: next check in {minutes} minutes")
            await asyncio.sleep(minutes * 60)
            return

        # daily mode: check every 30 seconds
        beijing_tz = timezone(timedelta(hours=8))
        while self._is_polling:
            now = datetime.now(beijing_tz)
            current_time = now.strftime("%H:%M")
            today_str = now.strftime("%Y-%m-%d")

            # Clear old day's trigger records
            old_keys = [k for k in self._triggered_today if not k.startswith(today_str)]
            for k in old_keys:
                self._triggered_today.discard(k)

            for t in cron["times"]:
                trigger_key = f"{today_str}_{t}"
                if current_time == t and trigger_key not in self._triggered_today:
                    self._triggered_today.add(trigger_key)
                    logger.info(f"[REFRESH] daily trigger: {t}")
                    return

            await asyncio.sleep(30)

    # ---- polling loop ----

    async def start_polling(self) -> None:
        """Main polling loop — runs until cancelled."""
        if self._is_polling:
            logger.warning("[REFRESH] polling already running")
            return

        self._is_polling = True
        logger.info("[REFRESH] smart refresh scheduler started")
        try:
            while self._is_polling:
                # Hot-reload config from database each cycle
                try:
                    config_manager.reload()
                except Exception as exc:
                    logger.warning("[REFRESH] config reload failed: %s", exc)

                if not config.retry.scheduled_refresh_enabled:
                    logger.debug("[REFRESH] scheduled refresh disabled, sleeping")
                    await asyncio.sleep(CONFIG_CHECK_INTERVAL_SECONDS)
                    continue

                # Wait for next trigger time (cron or interval)
                await self._wait_for_next_trigger()
                if not self._is_polling:
                    break

                await self.run_once(
                    trigger="scheduled",
                    reload_config=False,
                    allow_when_disabled=False,
                )

        except asyncio.CancelledError:
            logger.info("[REFRESH] polling stopped")
        except Exception as exc:
            logger.error("[REFRESH] polling error: %s", exc)
        finally:
            self._is_polling = False

    def stop_polling(self) -> None:
        self._is_polling = False
        logger.info("[REFRESH] stopping polling")
