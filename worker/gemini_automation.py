"""
Gemini自动化登录模块（支持账号刷新和新账号注册）
"""
import os
import json
import random
import re
import string
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from DrissionPage import ChromiumPage, ChromiumOptions
from worker.refresh_service import TaskCancelledError


# 常量
AUTH_HOME_URL = "https://auth.business.gemini.google/login"

# Linux 下常见的 Chromium 路径
CHROMIUM_PATHS = [
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
]

# 注册时随机使用的真实英文姓名（避免明显的机器人特征）
REGISTER_NAMES = [
    "James Smith", "John Johnson", "Robert Williams", "Michael Brown", "William Jones",
    "David Garcia", "Mary Miller", "Patricia Davis", "Jennifer Rodriguez", "Linda Martinez",
    "Barbara Anderson", "Susan Thomas", "Jessica Jackson", "Sarah White", "Karen Harris",
    "Lisa Martin", "Nancy Thompson", "Betty Garcia", "Margaret Martinez", "Sandra Robinson",
    "Ashley Clark", "Dorothy Rodriguez", "Emma Lewis", "Olivia Lee", "Ava Walker",
    "Emily Hall", "Abigail Allen", "Madison Young", "Elizabeth Hernandez", "Charlotte King",
]

# 常见桌面分辨率（避免固定 1280x800 成为指纹）
COMMON_VIEWPORTS = [
    (1366, 768), (1440, 900), (1536, 864), (1280, 720),
    (1920, 1080), (1600, 900), (1280, 800), (1360, 768),
]

BROWSER_MODE_NORMAL = "normal"
BROWSER_MODE_SILENT = "silent"
BROWSER_MODE_HEADLESS = "headless"


def _find_chromium_path() -> Optional[str]:
    """查找可用的 Chromium/Chrome 浏览器路径"""
    for path in CHROMIUM_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _data_file_path(name: str) -> str:
    """Worker local data directory helper."""
    return os.path.join("data", name)


def _normalize_browser_mode(mode: str, default: str = BROWSER_MODE_NORMAL) -> str:
    value = (mode or "").strip().lower()
    if value in (BROWSER_MODE_NORMAL, BROWSER_MODE_SILENT, BROWSER_MODE_HEADLESS):
        return value
    return default


class GeminiAutomation:
    """Gemini自动化登录（支持刷新和注册）"""

    def __init__(
        self,
        user_agent: str = "",
        proxy: str = "",
        headless: bool = True,
        browser_mode: str = "",
        timeout: int = 60,
        log_callback=None,
    ) -> None:
        self.user_agent = user_agent or self._get_ua()
        self.proxy = proxy
        default_mode = BROWSER_MODE_HEADLESS if headless else BROWSER_MODE_NORMAL
        self.browser_mode = _normalize_browser_mode(browser_mode, default_mode)
        self.headless = self.browser_mode == BROWSER_MODE_HEADLESS
        self.timeout = timeout
        self.log_callback = log_callback
        self._page = None
        self._user_data_dir = None
        self._last_send_error = ""
        self._last_send_confidence = "unknown"

    def stop(self) -> None:
        """外部请求停止：尽力关闭浏览器实例。"""
        page = self._page
        if page:
            try:
                page.quit()
            except Exception:
                pass

    def login_and_extract(self, email: str, mail_client, is_new_account: bool = False) -> dict:
        """执行登录并提取配置"""
        page = None
        user_data_dir = None
        try:
            page = self._create_page()
            user_data_dir = getattr(page, 'user_data_dir', None)
            self._page = page
            self._user_data_dir = user_data_dir
            return self._run_flow(page, email, mail_client, is_new_account=is_new_account)
        except TaskCancelledError:
            raise
        except Exception as exc:
            self._log("error", f"automation error: {exc}")
            return {"success": False, "error": str(exc)}
        finally:
            if page:
                try:
                    page.quit()
                except Exception:
                    pass
            self._page = None
            self._cleanup_user_data(user_data_dir)
            self._user_data_dir = None

    def _create_page(self) -> ChromiumPage:
        """创建浏览器页面"""
        options = ChromiumOptions()

        # 自动检测 Chromium 浏览器路径（Linux/Docker 环境）
        chromium_path = _find_chromium_path()
        if chromium_path:
            options.set_browser_path(chromium_path)

        options.set_argument("--incognito")
        options.set_argument("--no-sandbox")
        options.set_argument("--disable-dev-shm-usage")
        options.set_argument("--disable-setuid-sandbox")
        options.set_argument("--disable-blink-features=AutomationControlled")

        # 随机窗口尺寸（避免固定分辨率成为指纹）
        vw, vh = random.choice(COMMON_VIEWPORTS)
        options.set_argument(f"--window-size={vw},{vh}")
        options.set_user_agent(self.user_agent)

        # 防止 WebRTC 泄露真实 IP
        options.set_argument("--disable-webrtc")
        options.set_argument("--enforce-webrtc-ip-handling-policy")
        options.set_pref("webrtc.ip_handling_policy", "disable_non_proxied_udp")
        options.set_pref("webrtc.multiple_routes_enabled", False)
        options.set_pref("webrtc.nonproxied_udp_enabled", False)

        # 语言设置（确保使用中文界面）
        options.set_argument("--lang=zh-CN")
        options.set_pref("intl.accept_languages", "zh-CN,zh")

        if self.proxy:
            options.set_argument(f"--proxy-server={self.proxy}")

        if self.browser_mode == BROWSER_MODE_HEADLESS:
            # 使用新版无头模式，更接近真实浏览器
            options.set_argument("--headless=new")
            options.set_argument("--disable-gpu")
            options.set_argument("--no-first-run")
            options.set_argument("--disable-extensions")
            # 反检测参数
            options.set_argument("--disable-infobars")
            options.set_argument("--enable-features=NetworkService,NetworkServiceInProcess")
        elif self.browser_mode == BROWSER_MODE_SILENT:
            # 静默模式：有头运行，但尽量最小化，减少抢占焦点
            options.set_argument("--start-minimized")

        options.auto_port()
        page = ChromiumPage(options)
        page.set.timeouts(self.timeout)
        if self.browser_mode == BROWSER_MODE_SILENT:
            self._minimize_window(page)

        # 最小化 JS 注入：只设置 window.chrome（不使用 Object.defineProperty，避免被 reCAPTCHA 检测）
        try:
            page.run_cdp("Page.addScriptToEvaluateOnNewDocument", source="""
                if (!window.chrome) {
                    window.chrome = {runtime: {}, loadTimes: function(){return {}}, csi: function(){return {}}};
                }
            """)
        except Exception:
            pass

        return page

    def _minimize_window(self, page) -> None:
        """尽力将窗口最小化，避免抢占焦点。"""
        try:
            info = page.run_cdp("Browser.getWindowForTarget")
            if isinstance(info, dict) and info.get("windowId") is not None:
                page.run_cdp(
                    "Browser.setWindowBounds",
                    windowId=info["windowId"],
                    bounds={"windowState": "minimized"},
                )
        except Exception:
            # 有些环境（如无头/Xvfb）不支持窗口状态控制，静默忽略。
            pass

    def _extract_xsrf_token(self, page) -> str:
        """从页面中提取真实的 XSRF Token（避免硬编码被标黑）"""
        try:
            html = page.html or ""
            # 尝试从 meta 标签提取
            m = re.search(r'name=["\']xsrf-token["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
            if m:
                self._log("info", "🔑 从 meta 标签提取到 XSRF token")
                return m.group(1)
            # 尝试从隐藏 input 提取
            m = re.search(r'name=["\']xsrfToken["\'][^>]*value=["\']([A-Za-z0-9_-]{20,})["\']', html)
            if m:
                self._log("info", "🔑 从 input 提取到 XSRF token")
                return m.group(1)
            # 尝试从 JS 变量提取
            m = re.search(r'xsrfToken["\']?\s*[=:]\s*["\']([A-Za-z0-9_-]{20,})["\']', html)
            if m:
                self._log("info", "🔑 从 JS 提取到 XSRF token")
                return m.group(1)
            # 尝试从 URL 参数提取
            m = re.search(r'xsrfToken=([A-Za-z0-9_-]{20,})', html)
            if m:
                self._log("info", "🔑 从 URL 参数提取到 XSRF token")
                return m.group(1)
        except Exception as e:
            self._log("warning", f"⚠️ XSRF token 提取异常: {e}")
        self._log("warning", "⚠️ 未能从页面提取 XSRF token，使用备用值")
        return "GXO_B0wnNhs6UQJZMcrSbTsbEEs"

    def _run_flow(self, page, email: str, mail_client, is_new_account: bool = False) -> dict:
        """执行登录流程（is_new_account=True 时启用注册专用的增强用户名处理）"""

        # 记录任务开始时间，用于邮件时间过滤（全流程固定，不随重发更新）
        from datetime import datetime
        task_start_time = datetime.now()

        # Step 1: 导航到登录页面
        self._log("info", f"🌐 打开登录页面: {email}")
        page.get(AUTH_HOME_URL, timeout=self.timeout)
        time.sleep(random.uniform(2, 4))

        # 从页面动态提取 XSRF token（避免硬编码被 Google 标黑）
        xsrf_token = self._extract_xsrf_token(page)

        # 设置 XSRF Cookie
        try:
            self._log("info", "🍪 设置 XSRF Cookie...")
            page.set.cookies({
                "name": "__Host-AP_SignInXsrf",
                "value": xsrf_token,
                "url": AUTH_HOME_URL,
                "path": "/",
                "secure": True,
            })
        except Exception as e:
            self._log("warning", f"⚠️ Cookie 设置失败: {e}")

        # Step 1.5: 通过 URL 方式提交邮箱（稳定，不触发风控）
        login_hint = quote(email, safe="")
        login_url = f"https://auth.business.gemini.google/login/email?continueUrl=https%3A%2F%2Fbusiness.gemini.google%2F&loginHint={login_hint}&xsrfToken={xsrf_token}"

        # 先启动网络监听，再导航（避免漏掉页面加载期间的请求）
        try:
            page.listen.start(
                targets=["batchexecute"],
                is_regex=False,
                method=("POST",),
                res_type=("XHR", "FETCH"),
            )
        except Exception:
            pass

        self._log("info", "📧 使用 URL 方式提交邮箱...")
        page.get(login_url, timeout=self.timeout)
        time.sleep(random.uniform(3, 5))

        # 模拟真实用户行为：页面加载后随机滚动
        self._random_scroll(page)

        # Step 2: 检查当前页面状态
        current_url = page.url
        self._log("info", f"📍 当前 URL: {current_url}")

        # 检测 signin-error 页面（极端情况，一般 URL 方式不会触发）
        if "signin-error" in current_url:
            self._log("error", "❌ 进入 signin-error 页面，可能是代理或网络问题")
            self._save_screenshot(page, "signin_error")
            return {"success": False, "error": "signin-error: token rejected by Google, try changing proxy"}

        has_business_params = "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url

        if has_business_params:
            self._log("info", "✅ 已登录，提取配置")
            return self._extract_config(page, email)

        # 检测 403 Access Restricted（刷新/登录时账户可能已被封禁）
        access_error = self._check_access_restricted(page, email)
        if access_error:
            return access_error

        # Step 3: 点击发送验证码按钮（最多5轮，适度退避间隔）
        self._log("info", "📧 发送验证码...")
        max_send_rounds = 5
        send_round_delays = [10, 10, 15, 15, 20]
        send_round = 0
        while True:
            send_round += 1
            if self._click_send_code_button(page):
                break
            if send_round >= max_send_rounds:
                self._log("error", "❌ 验证码发送失败（可能触发风控），建议更换代理IP")
                self._save_screenshot(page, "send_code_button_failed")
                return {"success": False, "error": "send code failed after retries"}
            delay = send_round_delays[min(send_round - 1, len(send_round_delays) - 1)]
            self._log("warning", f"⚠️ 发送失败，{delay}秒后重试 ({send_round}/{max_send_rounds})")
            time.sleep(delay)

        # Step 4: 等待验证码输入框出现
        code_input = self._wait_for_code_input(page)
        if not code_input:
            self._log("error", "❌ 验证码输入框未出现")
            self._save_screenshot(page, "code_input_missing")
            return {"success": False, "error": "code input not found"}

        # Step 5: 轮询邮件获取验证码（3次，每次5秒间隔）
        self._log("info", "📬 等待邮箱验证码...")
        poll_since_time = task_start_time - timedelta(seconds=30)
        first_timeout = 30 if self._last_send_confidence == "confirmed" else 20
        self._log("info", f"📬 等待邮箱验证码 (窗口 {first_timeout}s, 发送状态={self._last_send_confidence})")
        code = mail_client.poll_for_code(timeout=first_timeout, interval=5, since_time=poll_since_time)

        if not code:
            from worker.config import config

            resend_attempts = int(getattr(config.retry, "verification_code_resend_count", 2) or 0)
            resend_attempts = max(0, min(5, resend_attempts))
            if resend_attempts <= 0:
                self._log("error", "❌ 验证码超时且未启用重发")
                self._save_screenshot(page, "code_timeout")
                return {"success": False, "error": "verification code timeout"}

            for resend_index in range(1, resend_attempts + 1):
                self._log("warning", f"⚠️ 验证码超时，尝试第 {resend_index}/{resend_attempts} 次重发...")
                time.sleep(random.uniform(1.0, 2.0))

                if not self._click_resend_code_button(page):
                    self._log("warning", f"⚠️ 未找到重发按钮 ({resend_index}/{resend_attempts})")
                    continue

                resend_timeout = 25 if self._last_send_confidence == "confirmed" else 15
                self._log("info", f"📬 已执行重发，继续轮询 (窗口 {resend_timeout}s, 发送状态={self._last_send_confidence}, 第 {resend_index} 次重发)")
                code = mail_client.poll_for_code(timeout=resend_timeout, interval=5, since_time=poll_since_time)
                if code:
                    break

            if not code:
                self._log("error", "❌ 多次重发后仍未收到验证码")
                self._save_screenshot(page, "code_timeout_after_resend")
                return {"success": False, "error": "verification code timeout after resend retries"}
        self._log("info", f"✅ 收到验证码: {code}")

        # Step 6: 输入验证码并提交
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=3) or \
                     page.ele("css:input[type='tel']", timeout=2)

        if not code_input:
            self._log("error", "❌ 验证码输入框已失效")
            return {"success": False, "error": "code input expired"}

        # 尝试模拟人类输入，失败则降级到直接注入
        self._log("info", "⌨️ 输入验证码...")
        if not self._simulate_human_input(code_input, code):
            self._log("warning", "⚠️ 模拟输入失败，降级为直接输入")
            code_input.input(code, clear=True)
            time.sleep(random.uniform(0.4, 0.8))

        # 提交验证码：先回车，再找验证按钮兜底
        self._log("info", "⏎ 提交验证码")
        code_input.input("\n")
        time.sleep(random.uniform(1, 2))
        # 如果回车没触发，找验证按钮点击
        if "verify-oob-code" in page.url:
            verify_btn = self._find_verify_button(page)
            if verify_btn:
                try:
                    verify_btn.click()
                    self._log("info", "✅ 已点击验证按钮（兜底）")
                except Exception:
                    pass

        # [注册专用] 验证码提交后先等几秒让页面跳转，再检查 403
        if is_new_account:
            time.sleep(3)
            access_error = self._check_access_restricted(page, email)
            if access_error:
                return access_error
            self._log("info", "📝 [注册] 验证码已提交，等待姓名输入页面...")
            if self._handle_username_setup(page, is_new_account=True):
                self._log("info", "✅ 姓名填写完成，等待工作台 URL...")
                if self._wait_for_business_params(page, timeout=45):
                    self._log("info", "🎊 注册成功，提取配置...")
                    return self._extract_config(page, email)
            # 姓名步骤失败或未出现，继续走通用流程兜底
            self._log("info", "⚠️ 姓名步骤未完成，走通用流程兜底...")

        # Step 7: 等待页面自动重定向（提交验证码后 Google 会自动跳转）
        self._log("info", "⏳ 等待验证后跳转...")
        time.sleep(random.uniform(10, 15))

        # 记录当前 URL 状态
        current_url = page.url
        self._log("info", f"📍 验证后 URL: {current_url}")

        # 检查是否还停留在验证码页面（说明提交失败）
        if "verify-oob-code" in current_url:
            self._log("error", "❌ 验证码提交失败")
            self._save_screenshot(page, "verification_submit_failed")
            return {"success": False, "error": "verification code submission failed"}

        # Step 8: 处理协议页面（如果有）
        self._handle_agreement_page(page)

        # Step 8.5: 检测 403 Access Restricted 页面
        access_error = self._check_access_restricted(page, email)
        if access_error:
            return access_error

        # Step 9: 检查是否已经在正确的页面
        current_url = page.url
        has_business_params = "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url

        if has_business_params:
            return self._extract_config(page, email)

        # Step 10: 如果不在正确的页面，尝试导航
        if "business.gemini.google" not in current_url:
            page.get("https://business.gemini.google/", timeout=self.timeout)
            time.sleep(random.uniform(4, 7))

        # Step 11: 检查是否需要设置用户名（仅登录刷新走此路径，注册已在早期处理）
        if not is_new_account and "cid" not in page.url:
            if self._handle_username_setup(page):
                time.sleep(random.uniform(4, 7))

        # Step 12: 再次检测 403（导航后可能出现）
        access_error = self._check_access_restricted(page, email)
        if access_error:
            return access_error

        # Step 13: 等待 URL 参数生成（csesidx 和 cid）
        if not self._wait_for_business_params(page):
            page.refresh()
            time.sleep(random.uniform(4, 7))
            if not self._wait_for_business_params(page):
                self._log("error", "❌ URL 参数生成失败")
                self._save_screenshot(page, "params_missing")
                return {"success": False, "error": "URL parameters not found"}

        # Step 13: 提取配置
        self._log("info", "🎊 登录成功，提取配置...")
        return self._extract_config(page, email)

    def _click_send_code_button(self, page) -> bool:
        """点击发送验证码按钮（如果需要）"""
        time.sleep(random.uniform(1.5, 3))
        try:
            page.listen.start(
                targets=["batchexecute"],
                is_regex=False,
                method=("POST",),
                res_type=("XHR", "FETCH"),
            )
        except Exception:
            pass
        max_send_attempts = 5
        # 适度退避延迟序列（秒）
        retry_delays = [10, 10, 15, 15, 20]

        # 方法1: 直接通过ID查找
        direct_btn = page.ele("#sign-in-with-email", timeout=5)
        if direct_btn:
            for attempt in range(1, max_send_attempts + 1):
                try:
                    self._last_send_error = ""
                    self._human_click(page, direct_btn)
                    if self._evaluate_send_after_click(page):
                        self._stop_listen(page)
                        return True
                    delay = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
                    if self._last_send_error == "captcha_check_failed":
                        self._log("error", f"❌ 触发风控，建议更换代理IP ({attempt}/{max_send_attempts})")
                    else:
                        self._log("warning", f"⚠️ 发送失败，{delay}秒后重试 ({attempt}/{max_send_attempts})")
                    time.sleep(delay)
                except Exception as e:
                    self._log("warning", f"⚠️ 点击失败: {e}")
            self._stop_listen(page)
            return False

        # 方法2: 通过关键词查找
        keywords = ["通过电子邮件发送验证码", "通过电子邮件发送", "email", "Email", "Send code", "Send verification", "Verification code"]
        try:
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip()
                if text and any(kw in text for kw in keywords):
                    for attempt in range(1, max_send_attempts + 1):
                        try:
                            self._last_send_error = ""
                            self._human_click(page, btn)
                            if self._evaluate_send_after_click(page):
                                self._stop_listen(page)
                                return True
                            delay = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
                            if self._last_send_error == "captcha_check_failed":
                                self._log("error", f"❌ 触发风控，建议更换代理IP ({attempt}/{max_send_attempts})")
                            else:
                                self._log("warning", f"⚠️ 发送失败，{delay}秒后重试 ({attempt}/{max_send_attempts})")
                            time.sleep(delay)
                        except Exception as e:
                            self._log("warning", f"⚠️ 点击失败: {e}")
                    self._stop_listen(page)
                    return False
        except Exception as e:
            self._log("warning", f"⚠️ 搜索按钮异常: {e}")

        # 检查是否在 signin-error 页面（不应该继续尝试发送）
        if "signin-error" in (page.url or ""):
            self._stop_listen(page)
            self._log("error", "❌ 在 signin-error 页面，无法发送验证码")
            return False

        # 检查是否已经在验证码输入页面
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=2) or page.ele("css:input[name='pinInput']", timeout=1)
        if code_input:
            self._stop_listen(page)
            self._log("info", "✅ 已在验证码输入页面")

            # 直接点击重新发送按钮（不管之前是否发送过）
            if self._click_resend_code_button(page):
                self._log("info", "✅ 已点击重新发送按钮")
                return True
            else:
                self._log("warning", "⚠️ 未找到重新发送按钮，继续流程")
                return True

        self._stop_listen(page)
        self._log("error", "❌ 未找到发送验证码按钮")
        return False

    def _stop_listen(self, page) -> None:
        """安全地停止网络监听"""
        try:
            if hasattr(page, 'listen') and page.listen:
                page.listen.stop()
        except Exception:
            pass


    def _evaluate_send_after_click(self, page) -> bool:
        """Evaluate send-code click result with network/UI fallback."""
        network_ok = self._verify_code_send_by_network(page)
        ui_state = self._verify_code_send_status(page)
        if self._last_send_error or ui_state is False:
            self._last_send_confidence = "failed"
            return False
        if network_ok or ui_state is True:
            self._last_send_confidence = "confirmed"
            return True
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=2) or page.ele("css:input[name='pinInput']", timeout=1)
        if code_input:
            self._last_send_confidence = "unknown"
            return True
        self._last_send_confidence = "unknown"
        return False

    def _verify_code_send_by_network(self, page) -> bool:
        """通过监听网络请求验证验证码是否成功发送"""
        try:
            time.sleep(1)

            packets = []
            max_wait_seconds = 6
            deadline = time.time() + max_wait_seconds
            try:
                while time.time() < deadline:
                    got_any = False
                    for packet in page.listen.steps(timeout=1, gap=1):
                        packets.append(packet)
                        got_any = True
                    if got_any:
                        time.sleep(0.2)
                    else:
                        break
            except Exception:
                return False

            if not packets:
                return False

            # 保存网络日志（仅用于调试）
            save_packets = os.getenv("SAVE_NETWORK_PACKETS", "").strip().lower() in ("1", "true", "yes", "y", "on")
            if save_packets:
                self._save_network_packets(packets)

            found_batchexecute = False
            found_relevant_packet = False
            found_batchexecute_error = False

            for packet in packets:
                try:
                    url = str(packet.url) if hasattr(packet, 'url') else str(packet)

                    if 'batchexecute' in url:
                        found_batchexecute = True

                        try:
                            request = packet.request if hasattr(packet, 'request') else None
                            response = packet.response if hasattr(packet, 'response') else None
                            request_body = str(request.postData) if request and hasattr(request, 'postData') else ""
                            response_body = str(response.raw_body) if response and hasattr(response, 'raw_body') else ""
                            payload_lower = f"{request_body}\n{response_body}".lower()

                            if any(token in payload_lower for token in ("sendemailotp", "send_email_otp", "emailotp", "otp")):
                                found_relevant_packet = True

                            if response and hasattr(response, 'raw_body'):
                                raw_body_str = str(response.raw_body)
                                if "CAPTCHA_CHECK_FAILED" in raw_body_str:
                                    found_batchexecute_error = True
                                    found_relevant_packet = True
                                    self._last_send_error = "captcha_check_failed"
                                elif "SendEmailOtpError" in raw_body_str:
                                    found_batchexecute_error = True
                                    found_relevant_packet = True
                                    self._last_send_error = "send_email_otp_error"
                        except Exception:
                            pass

                except Exception:
                    continue

            if found_batchexecute and found_relevant_packet:
                if found_batchexecute_error:
                    return False
                return True
            else:
                return False

        except Exception:
            return False

    def _verify_code_send_status(self, page) -> Optional[bool]:
        """检测页面提示判断是否发送成功"""
        time.sleep(random.uniform(1.5, 3))
        try:
            success_keywords = ["验证码已发送", "code sent", "email sent", "check your email", "已发送"]
            error_keywords = [
                "出了点问题",
                "something went wrong",
                "error",
                "failed",
                "try again",
                "稍后再试",
                "选择其他登录方法"
            ]
            selectors = [
                "css:.zyTWof-gIZMF",
                "css:[role='alert']",
                "css:aside",
            ]
            for selector in selectors:
                try:
                    elements = page.eles(selector, timeout=1)
                    for elem in elements[:20]:
                        text = (elem.text or "").strip()
                        if not text:
                            continue
                        if any(kw in text for kw in error_keywords):
                            return False
                        if any(kw in text for kw in success_keywords):
                            return True
                except Exception:
                    continue
            return None
        except Exception:
            return None

    def _truncate_text(self, text: str, max_len: int = 2000) -> str:
        if text is None:
            return ""
        if len(text) <= max_len:
            return text
        return text[:max_len] + f"...(truncated, total={len(text)})"

    def _save_network_packets(self, packets) -> None:
        """保存网络日志（仅用于调试）"""
        try:
            base_dir = _data_file_path(os.path.join("logs", "network"))
            os.makedirs(base_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            file_path = os.path.join(base_dir, f"network-{ts}.jsonl")

            def safe_str(value):
                try:
                    return value if isinstance(value, str) else str(value)
                except Exception:
                    return "<unprintable>"

            with open(file_path, "a", encoding="utf-8") as f:
                for packet in packets:
                    try:
                        req = packet.request if hasattr(packet, "request") else None
                        resp = packet.response if hasattr(packet, "response") else None
                        fail = packet.fail_info if hasattr(packet, "fail_info") else None

                        item = {
                            "url": safe_str(packet.url) if hasattr(packet, "url") else safe_str(packet),
                            "method": safe_str(packet.method) if hasattr(packet, "method") else "UNKNOWN",
                            "resourceType": safe_str(packet.resourceType) if hasattr(packet, "resourceType") else "",
                            "is_failed": bool(packet.is_failed) if hasattr(packet, "is_failed") else False,
                            "fail_info": safe_str(fail) if fail else "",
                            "request": {
                                "headers": req.headers if req and hasattr(req, "headers") else {},
                                "postData": req.postData if req and hasattr(req, "postData") else "",
                            },
                            "response": {
                                "status": resp.status if resp and hasattr(resp, "status") else 0,
                                "headers": resp.headers if resp and hasattr(resp, "headers") else {},
                                "raw_body": resp.raw_body if resp and hasattr(resp, "raw_body") else "",
                            },
                        }
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                    except Exception as e:
                        f.write(json.dumps({"error": safe_str(e)}, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _wait_for_code_input(self, page, timeout: int = 30):
        """等待验证码输入框出现"""
        selectors = [
            "css:input[jsname='ovqh0b']",
            "css:input[type='tel']",
            "css:input[name='pinInput']",
            "css:input[autocomplete='one-time-code']",
        ]
        for _ in range(timeout // 2):
            for selector in selectors:
                try:
                    el = page.ele(selector, timeout=1)
                    if el:
                        return el
                except Exception:
                    continue
            time.sleep(2)
        return None

    def _simulate_human_input(self, element, text: str) -> bool:
        """模拟人类输入（逐字符输入，带非均匀延迟）"""
        try:
            # 先点击输入框获取焦点
            element.click()
            time.sleep(random.uniform(0.2, 0.5))

            # 逐字符输入，模拟真实打字节奏
            for i, char in enumerate(text):
                element.input(char)
                # 基础延迟 80-180ms（正常打字速度）
                delay = random.uniform(0.08, 0.18)
                # 每3-5个字符偶尔有更长的停顿
                if i > 0 and random.random() < 0.2:
                    delay += random.uniform(0.2, 0.5)
                time.sleep(delay)

            # 输入完成后停顿（模拟核对）
            time.sleep(random.uniform(0.3, 0.8))
            return True
        except Exception:
            return False

    def _human_click(self, page, element) -> None:
        """模拟人类点击：先移动鼠标到元素附近，再点击"""
        try:
            page.actions.move_to(element)
            time.sleep(random.uniform(0.1, 0.3))
            page.actions.click()
        except Exception:
            # 降级为直接点击
            element.click()

    def _random_scroll(self, page) -> None:
        """模拟真实用户的页面滚动行为"""
        try:
            scroll_amount = random.randint(50, 200)
            page.run_js(f"window.scrollBy(0, {scroll_amount})")
            time.sleep(random.uniform(0.3, 0.8))
            # 有时候滚回去一点
            if random.random() < 0.3:
                page.run_js(f"window.scrollBy(0, -{random.randint(20, 80)})")
                time.sleep(random.uniform(0.2, 0.5))
        except Exception:
            pass

    def _find_verify_button(self, page):
        """查找验证按钮（排除重新发送按钮）"""
        try:
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip().lower()
                if text and "重新" not in text and "发送" not in text and "resend" not in text and "send" not in text:
                    return btn
        except Exception:
            pass
        return None

    def _click_resend_code_button(self, page) -> bool:
        """点击重新发送验证码按钮"""
        time.sleep(random.uniform(1.5, 3))
        try:
            page.listen.start(
                targets=["batchexecute"],
                is_regex=False,
                method=("POST",),
                res_type=("XHR", "FETCH"),
            )
        except Exception:
            pass

        # 查找包含重新发送关键词的按钮（与 _find_verify_button 相反）
        try:
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip().lower()
                if text and ("重新" in text or "resend" in text):
                    try:
                        self._log("info", f"🔄 点击重新发送按钮")
                        self._human_click(page, btn)
                        network_ok = self._verify_code_send_by_network(page)
                        ui_state = self._verify_code_send_status(page)
                        if self._last_send_error or ui_state is False:
                            self._last_send_confidence = "failed"
                            self._stop_listen(page)
                            return False
                        if network_ok or ui_state is True:
                            self._last_send_confidence = "confirmed"
                        else:
                            self._last_send_confidence = "unknown"
                        self._stop_listen(page)
                        return True
                    except Exception:
                        pass
        except Exception:
            pass

        self._last_send_confidence = "failed"
        self._stop_listen(page)
        return False

    def _handle_agreement_page(self, page) -> None:
        """处理协议页面"""
        if "/admin/create" in page.url:
            agree_btn = page.ele("css:button.agree-button", timeout=5)
            if agree_btn:
                self._human_click(page, agree_btn)
                time.sleep(random.uniform(2, 4))

    def _wait_for_cid(self, page, timeout: int = 10) -> bool:
        """等待URL包含cid"""
        for _ in range(timeout):
            if "cid" in page.url:
                return True
            time.sleep(1)
        return False

    def _wait_for_business_params(self, page, timeout: int = 30) -> bool:
        """等待业务页面参数生成（csesidx 和 cid）"""
        for _ in range(timeout):
            url = page.url
            if "csesidx=" in url and "/cid/" in url:
                return True
            time.sleep(1)
        return False

    def _handle_username_setup(self, page, is_new_account: bool = False) -> bool:
        """处理用户名设置页面（is_new_account=True 时启用按钮兜底和延长超时）"""
        current_url = page.url

        if "auth.business.gemini.google/login" in current_url:
            return False

        # 精准选择器
        selectors = [
            "css:input[formcontrolname='fullName']",
            "css:input#mat-input-0",
            "css:input[placeholder='全名']",
            "css:input[placeholder='Full name']",
            "css:input[name='displayName']",
            "css:input[aria-label*='用户名' i]",
            "css:input[aria-label*='display name' i]",
            "css:input[type='text']",
        ]

        # 轮询等待输入框出现（最多30秒）
        username_input = None
        self._log("info", "⏳ 等待用户名输入框出现（最多30秒）...")
        for _ in range(30):
            for selector in selectors:
                try:
                    el = page.ele(selector, timeout=1)
                    if el:
                        username_input = el
                        self._log("info", f"✅ 找到用户名输入框: {selector}")
                        break
                except Exception:
                    continue
            if username_input:
                break
            time.sleep(1)

        if not username_input:
            self._log("warning", "⚠️ 30秒内未找到用户名输入框，跳过此步骤")
            return False

        name = random.choice(REGISTER_NAMES)
        self._log("info", f"✏️ 输入姓名: {name}")

        try:
            # 清空输入框
            username_input.click()
            time.sleep(random.uniform(0.2, 0.5))
            username_input.clear()
            time.sleep(random.uniform(0.1, 0.3))

            # 尝试模拟人类输入，失败则降级到直接注入
            if not self._simulate_human_input(username_input, name):
                username_input.input(name)
                time.sleep(0.3)

            # 回车提交
            username_input.input("\n")

            if is_new_account:
                # 注册专用：回车后等待1.5秒，若未跳转则用按钮兜底
                time.sleep(random.uniform(1.5, 3))
                if "cid" not in page.url:
                    self._log("info", "⌨️ 回车未跳转，尝试点击提交按钮...")
                    try:
                        for btn in page.eles("tag:button"):
                            try:
                                if btn.is_displayed() and btn.is_enabled():
                                    btn.click()
                                    self._log("info", "✅ 已点击提交按钮（兜底）")
                                    time.sleep(1)
                                    break
                            except Exception:
                                continue
                    except Exception as e:
                        self._log("warning", f"⚠️ 按钮兜底失败: {e}")

                # 注册专用：等待45秒，失败则刷新再等15秒
                if not self._wait_for_cid(page, timeout=45):
                    self._log("warning", "⚠️ 用户名提交后未检测到 cid 参数，尝试刷新...")
                    page.refresh()
                    time.sleep(random.uniform(2, 4))
                    if not self._wait_for_cid(page, timeout=15):
                        self._log("error", "❌ 刷新后仍未检测到 cid 参数")
                        self._save_screenshot(page, "step7_after_verify")
                        return False
            else:
                # 登录刷新：原有30秒逻辑
                if not self._wait_for_cid(page, timeout=30):
                    self._log("warning", "⚠️ 用户名提交后未检测到 cid 参数")
                    return False

            return True
        except Exception as e:
            self._log("warning", f"⚠️ 用户名设置异常: {e}")
            return False

    def _extract_config(self, page, email: str) -> dict:
        """提取配置（轮询等待 cookie 到位）"""
        try:
            if "cid/" not in page.url:
                page.get("https://business.gemini.google/", timeout=self.timeout)
                time.sleep(random.uniform(2, 4))

            url = page.url
            if "cid/" not in url:
                return {"success": False, "error": "cid not found"}

            config_id = url.split("cid/")[1].split("?")[0].split("/")[0]
            csesidx = url.split("csesidx=")[1].split("&")[0] if "csesidx=" in url else ""

            # 轮询等待关键 cookie 到位（最多10秒）
            ses = None
            host = None
            ses_obj = None
            for _ in range(10):
                cookies = page.cookies()
                ses = next((c["value"] for c in cookies if c["name"] == "__Secure-C_SES"), None)
                host = next((c["value"] for c in cookies if c["name"] == "__Host-C_OSES"), None)
                ses_obj = next((c for c in cookies if c["name"] == "__Secure-C_SES"), None)
                if ses and host:
                    break
                time.sleep(1)

            if not ses or not host:
                self._log("warning", f"⚠️ Cookie 不完整 (ses={'有' if ses else '无'}, host={'有' if host else '无'})")

            # 使用北京时区
            beijing_tz = timezone(timedelta(hours=8))
            if ses_obj and "expiry" in ses_obj:
                cookie_expire_beijing = datetime.fromtimestamp(ses_obj["expiry"], tz=beijing_tz)
                expires_at = (cookie_expire_beijing - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                expires_at = (datetime.now(beijing_tz) + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")

            config = {
                "id": email,
                "csesidx": csesidx,
                "config_id": config_id,
                "secure_c_ses": ses,
                "host_c_oses": host,
                "expires_at": expires_at,
            }

            # 提取试用期信息
            trial_end = self._extract_trial_end(page, csesidx, config_id)
            if trial_end:
                config["trial_end"] = trial_end

            return {"success": True, "config": config}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_trial_end(self, page, csesidx: str, config_id: str) -> Optional[str]:
        """从页面中提取试用期到期日期"""
        try:
            self._log("info", "📅 获取试用期信息...")

            def _days_to_end_date(days: int) -> str:
                end_date = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=days)).strftime("%Y-%m-%d")
                self._log("info", f"📅 试用期剩余 {days} 天，到期日: {end_date}")
                return end_date

            def _search_page_source(source: str) -> Optional[str]:
                """在页面源码中搜索试用期信息"""
                # 格式1: "daysLeft":29
                m = re.search(r'"daysLeft"\s*:\s*(\d+)', source)
                if m:
                    return _days_to_end_date(int(m.group(1)))
                # 格式2: "trialDaysRemaining":29
                m = re.search(r'"trialDaysRemaining"\s*:\s*(\d+)', source)
                if m:
                    return _days_to_end_date(int(m.group(1)))
                # 格式3: 日期数组 "[2026,3,25]" 形式
                m = re.search(r'\[(\d{4}),(\d{1,2}),(\d{1,2})\].*?\[(\d{4}),(\d{1,2}),(\d{1,2})\]', source)
                if m:
                    try:
                        end_date = f"{m.group(4):0>4}-{int(m.group(5)):02d}-{int(m.group(6)):02d}"
                        if 2025 <= int(m.group(4)) <= 2030:
                            self._log("info", f"📅 试用期到期日: {end_date}")
                            return end_date
                    except Exception:
                        pass
                # 格式4: "29 days left" 或 "还剩29天"
                m = re.search(r'(\d+)\s*days?\s*left', source, re.IGNORECASE)
                if m:
                    return _days_to_end_date(int(m.group(1)))
                m = re.search(r'还剩\s*(\d+)\s*天', source)
                if m:
                    return _days_to_end_date(int(m.group(1)))
                return None

            # ——— 方式1: 当前页面 ———
            try:
                source = page.html
                result = _search_page_source(source or "")
                if result:
                    return result
            except Exception:
                pass

            # ——— 方式2: 跳转到 /settings ———
            try:
                settings_url = f"https://business.gemini.google/cid/{config_id}/settings?csesidx={csesidx}"
                page.get(settings_url, timeout=self.timeout)
                time.sleep(random.uniform(1.5, 3))
                source = page.html
                result = _search_page_source(source or "")
                if result:
                    return result
            except Exception:
                pass

            # ——— 方式3: 跳转到主页 ———
            try:
                main_url = f"https://business.gemini.google/cid/{config_id}?csesidx={csesidx}"
                page.get(main_url, timeout=self.timeout)
                time.sleep(random.uniform(1.5, 3))
                source = page.html
                result = _search_page_source(source or "")
                if result:
                    return result
            except Exception:
                pass

            self._log("warning", "⚠️ 未能获取试用期信息（页面中未找到相关数据）")
            return None
        except Exception as e:
            self._log("warning", f"⚠️ 获取试用期失败: {e}")
            return None

    def _check_access_restricted(self, page, email: str = "") -> dict | None:
        """检测 403 Access Restricted 页面，返回错误 dict 或 None"""
        domain = email.split("@")[1] if "@" in email else "unknown"
        error_msg = f"403 域名封禁 ({domain})"

        # 方法1: 搜索 h1 标签
        try:
            h1 = page.ele("tag:h1", timeout=2)
            h1_text = h1.text if h1 else ""
            if h1_text and "Access Restricted" in h1_text:
                self._log("error", "⛔ 403 Access Restricted: email banned by Google")
                self._log("error", f"⛔ 403 访问受限，域名 {domain} 可能已被 Google 封禁")
                self._save_screenshot(page, "access_restricted_403")
                return {"success": False, "error": error_msg}
        except Exception:
            pass

        # 方法2: body 文本
        try:
            body = page.ele("tag:body", timeout=2)
            body_text = (body.text or "")[:500] if body else ""
            if "Access Restricted" in body_text:
                self._log("error", "⛔ 403 Access Restricted: email banned by Google")
                self._log("error", f"⛔ 403 访问受限，域名 {domain} 可能已被 Google 封禁")
                self._save_screenshot(page, "access_restricted_403")
                return {"success": False, "error": error_msg}
        except Exception:
            pass

        # 方法3: page.html 源码
        try:
            html = (page.html or "")[:2000]
            if "Access Restricted" in html:
                self._log("error", "⛔ 403 Access Restricted: email banned by Google")
                self._log("error", f"⛔ 403 访问受限，域名 {domain} 可能已被 Google 封禁")
                self._save_screenshot(page, "access_restricted_403")
                return {"success": False, "error": error_msg}
        except Exception:
            pass

        return None

    def _save_screenshot(self, page, name: str) -> None:
        """保存截图"""
        try:
            screenshot_dir = _data_file_path("automation")
            os.makedirs(screenshot_dir, exist_ok=True)
            path = os.path.join(screenshot_dir, f"{name}_{int(time.time())}.png")
            page.get_screenshot(path=path)
        except Exception:
            pass

    def _log(self, level: str, message: str) -> None:
        """记录日志"""
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except TaskCancelledError:
                raise
            except Exception:
                pass

    def _cleanup_user_data(self, user_data_dir: Optional[str]) -> None:
        """清理浏览器用户数据目录"""
        if not user_data_dir:
            return
        try:
            import shutil
            if os.path.exists(user_data_dir):
                shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass

    @staticmethod
    def _get_ua() -> str:
        """生成随机User-Agent（使用当前主流 Chrome 版本）"""
        major = random.choice([132, 133, 134, 135])
        v = f"{major}.0.{random.randint(6800, 6950)}.{random.randint(50, 150)}"
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36"
