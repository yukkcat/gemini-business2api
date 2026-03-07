"""
账号注册服务模块 - 用于自动注册新 Gemini Business 账号
"""
import logging
import time
from typing import Optional, Callable

from worker.config import config_manager
from worker.mail_clients import create_temp_mail_client
from worker.gemini_automation import GeminiAutomation
from worker.proxy_utils import parse_proxy_setting
from worker import storage

logger = logging.getLogger("worker.register")


def register_one(
    domain: Optional[str] = None,
    mail_provider: Optional[str] = None,
    log_cb: Optional[Callable[[str, str], None]] = None,
) -> dict:
    """
    注册单个 Gemini Business 账户。

    流程:
    1. 通过临时邮箱服务创建新邮箱
    2. 使用浏览器自动化完成 Gemini Business 注册
    3. 提取账户凭据并保存到数据库

    Args:
        domain: 邮箱域名（DuckMail 专用）
        mail_provider: 临时邮箱提供商名称
        log_cb: 日志回调函数 (level, message)

    Returns:
        dict: {"success": True/False, "email": ..., "error": ...}
    """
    cfg = config_manager.config

    def _log(level: str, message: str):
        if log_cb:
            log_cb(level, message)
        getattr(logger, level, logger.info)(message)

    _log("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    _log("info", "🆕 开始注册新账户")
    _log("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 确定邮箱提供商
    temp_mail_provider = (mail_provider or "").strip().lower()
    if not temp_mail_provider:
        temp_mail_provider = (cfg.basic.temp_mail_provider or "duckmail").lower()

    # 确定邮箱域名
    domain_value = (domain or "").strip()
    if not domain_value:
        if temp_mail_provider == "duckmail":
            domain_value = (cfg.basic.register_domain or "").strip() or None
        else:
            domain_value = None

    _log("info", f"📧 步骤 1/3: 注册临时邮箱 (提供商={temp_mail_provider})...")

    if temp_mail_provider == "freemail" and not cfg.basic.freemail_jwt_token:
        _log("error", "❌ Freemail JWT Token 未配置")
        return {"success": False, "error": "Freemail JWT Token 未配置"}

    client = create_temp_mail_client(
        temp_mail_provider,
        domain=domain_value,
        log_cb=_log,
    )

    if not client.register_account(domain=domain_value):
        _log("error", f"❌ {temp_mail_provider} 邮箱注册失败")
        return {"success": False, "error": f"{temp_mail_provider} 注册失败"}

    _log("info", f"✅ 邮箱注册成功: {client.email}")

    browser_mode = (cfg.basic.browser_mode or "normal").strip().lower()
    headless = cfg.basic.browser_headless
    proxy_for_auth, _ = parse_proxy_setting(cfg.basic.proxy_for_auth)

    _log("info", f"🌐 步骤 2/3: 启动浏览器 (模式={browser_mode}, 无头={headless})...")

    automation = GeminiAutomation(
        proxy=proxy_for_auth,
        browser_mode=browser_mode,
        log_callback=_log,
    )

    try:
        _log("info", "🔐 步骤 3/3: 执行 Gemini 自动登录...")
        result = automation.login_and_extract(client.email, client, is_new_account=True)
    except Exception as exc:
        _log("error", f"❌ 自动登录异常: {exc}")
        return {"success": False, "error": str(exc)}

    if not result.get("success"):
        error = result.get("error", "自动化流程失败")
        _log("error", f"❌ 自动登录失败: {error}")
        return {"success": False, "error": error}

    _log("info", "✅ Gemini 登录成功，正在保存配置...")

    config_data = result["config"]
    config_data["mail_provider"] = temp_mail_provider
    config_data["mail_address"] = client.email

    # 保存邮箱提供商配置
    if temp_mail_provider == "freemail":
        config_data["mail_password"] = ""
        config_data["mail_base_url"] = cfg.basic.freemail_base_url
        config_data["mail_jwt_token"] = cfg.basic.freemail_jwt_token
        config_data["mail_verify_ssl"] = cfg.basic.freemail_verify_ssl
        config_data["mail_domain"] = cfg.basic.freemail_domain
    elif temp_mail_provider == "gptmail":
        config_data["mail_password"] = ""
        config_data["mail_base_url"] = cfg.basic.gptmail_base_url
        config_data["mail_api_key"] = cfg.basic.gptmail_api_key
        config_data["mail_verify_ssl"] = cfg.basic.gptmail_verify_ssl
        config_data["mail_domain"] = cfg.basic.gptmail_domain
    elif temp_mail_provider == "moemail":
        config_data["mail_password"] = getattr(client, "email_id", "") or getattr(client, "password", "")
        config_data["mail_base_url"] = cfg.basic.moemail_base_url
        config_data["mail_api_key"] = cfg.basic.moemail_api_key
        config_data["mail_domain"] = cfg.basic.moemail_domain
    elif temp_mail_provider == "duckmail":
        config_data["mail_password"] = getattr(client, "password", "")
        config_data["mail_base_url"] = cfg.basic.duckmail_base_url
        config_data["mail_api_key"] = cfg.basic.duckmail_api_key
    else:
        config_data["mail_password"] = getattr(client, "password", "")

    # 保存到数据库
    saved = storage.add_account_sync(config_data)
    if not saved:
        _log("error", "❌ 保存配置到数据库失败")
        return {"success": False, "error": "保存配置失败"}

    _log("info", "✅ 配置已保存到数据库")
    _log("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    _log("info", f"🎉 账户注册完成: {client.email}")
    _log("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return {"success": True, "email": client.email, "config": config_data}
