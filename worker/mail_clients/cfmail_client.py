"""
Cloudflare Temp Email client (cfmail provider).

API style (cloudflare_temp_email):
- GET  /open_api/settings
- POST /admin/new_address
- GET  /admin/mails?address=<addr>
"""

import random
import string
import time
from datetime import datetime
from typing import Optional

import requests

from worker.mail_utils import extract_verification_code
from worker.proxy_utils import request_with_proxy_fallback


class CloudflareMailClient:
    """Cloudflare Temp Email temporary mailbox client."""

    def __init__(
        self,
        base_url: str = "",
        proxy: str = "",
        api_key: str = "",
        domain: str = "",
        verify_ssl: bool = True,
        log_callback=None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.proxy_url = (proxy or "").strip()
        self.api_key = (api_key or "").strip()  # x-admin-auth
        self.domain = (domain or "").strip()
        self.verify_ssl = verify_ssl
        self.log_callback = log_callback

        self.email: Optional[str] = None
        self.password: Optional[str] = None  # compatibility: stores JWT
        self.jwt_token: Optional[str] = None
        self._available_domains: list[str] = []

    def _log(self, level: str, message: str) -> None:
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except Exception:
                pass

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", None) or {}
        lower_keys = {k.lower() for k in headers}

        if self.api_key and "x-admin-auth" not in lower_keys:
            headers["x-admin-auth"] = self.api_key

        if self.jwt_token and "authorization" not in lower_keys:
            headers["Authorization"] = f"Bearer {self.jwt_token}"

        kwargs["headers"] = headers

        self._log("info", f"📤 发送 {method} 请求: {url}")
        if "json" in kwargs and kwargs["json"] is not None:
            self._log("info", f"📦 请求体: {kwargs['json']}")

        proxies = {"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else None
        try:
            res = request_with_proxy_fallback(
                requests.request,
                method,
                url,
                proxies=proxies,
                verify=self.verify_ssl,
                timeout=kwargs.pop("timeout", 30),
                **kwargs,
            )
            self._log("info", f"📥 收到响应: HTTP {res.status_code}")
            if res.content and res.status_code >= 400:
                try:
                    self._log("error", f"📄 响应内容: {res.text[:500]}")
                except Exception:
                    pass
            return res
        except Exception as exc:
            self._log("error", f"❌ 网络请求失败: {exc}")
            raise

    def set_credentials(self, email: str, password: str = "") -> None:
        """Set mailbox address + JWT (password arg used as JWT token)."""
        self.email = email
        self.password = password
        if password:
            self.jwt_token = password

    def _get_available_domains(self) -> list[str]:
        if self._available_domains:
            return self._available_domains
        try:
            res = self._request("GET", f"{self.base_url}/open_api/settings")
            if res.status_code == 200:
                data = res.json() if res.content else {}
                domains = data.get("domains", [])
                if isinstance(domains, list) and domains:
                    self._available_domains = [str(d).strip() for d in domains if d]
                    self._log("info", f"🌐 CFMail 可用域名: {self._available_domains}")
        except Exception as exc:
            self._log("error", f"❌ 获取可用域名失败: {exc}")
        return self._available_domains

    def register_account(self, domain: Optional[str] = None) -> bool:
        if not self.base_url:
            self._log("error", "❌ cfmail_base_url 未配置")
            return False

        selected_domain = domain or self.domain
        if not selected_domain:
            available = self._get_available_domains()
            if available:
                selected_domain = random.choice(available)

        rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        timestamp = str(int(time.time()))[-4:]
        name = f"t{timestamp}{rand}"

        payload = {"name": name}
        if selected_domain:
            payload["domain"] = selected_domain
            self._log("info", f"📧 使用域名: {selected_domain}")

        self._log("info", f"🎲 创建邮箱: {name}")
        try:
            res = self._request("POST", f"{self.base_url}/admin/new_address", json=payload)
            if res.status_code in (200, 201):
                data = res.json() if res.content else {}
                address = data.get("address", "")
                jwt = data.get("jwt", "")
                if address:
                    self.email = address
                    self.jwt_token = jwt
                    self.password = jwt
                    self._log("info", f"✅ CFMail 注册成功: {self.email}")
                    return True
            self._log("error", f"❌ CFMail 注册失败: HTTP {res.status_code}")
            return False
        except Exception as exc:
            self._log("error", f"❌ CFMail 注册异常: {exc}")
            return False

    def login(self) -> bool:
        return True

    @staticmethod
    def _extract_body_from_raw(raw: str) -> str:
        if not raw:
            return ""
        import email as _email
        try:
            msg = _email.message_from_string(raw)
            parts = []
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct in ("text/plain", "text/html"):
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            parts.append(payload.decode(charset, errors="replace"))
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    parts.append(payload.decode(charset, errors="replace"))
            return "".join(parts)
        except Exception:
            return ""

    def fetch_verification_code(self, since_time: Optional[datetime] = None) -> Optional[str]:
        if not self.email:
            self._log("error", "❌ 缺少邮箱地址，无法获取邮件")
            return None

        try:
            self._log("info", "📬 正在拉取 CFMail 邮件列表...")
            res = self._request(
                "GET",
                f"{self.base_url}/admin/mails",
                params={"limit": 20, "offset": 0, "address": self.email},
            )
            if res.status_code != 200:
                self._log("error", f"❌ 获取邮件列表失败: HTTP {res.status_code}")
                return None

            data = res.json() if res.content else {}
            messages = data.get("results", [])
            if not isinstance(messages, list) or not messages:
                self._log("info", "📭 邮箱为空，暂无邮件")
                return None

            self._log("info", f"📨 收到 {len(messages)} 封邮件，开始检查验证码...")
            try:
                messages = sorted(messages, key=lambda m: int(m.get("id") or 0), reverse=True)
            except Exception:
                pass

            for idx, msg in enumerate(messages, 1):
                msg_id = msg.get("id")
                if not msg_id:
                    continue

                if since_time:
                    raw_time = msg.get("created_at") or msg.get("createdAt")
                    if raw_time:
                        try:
                            if isinstance(raw_time, (int, float)):
                                ts = float(raw_time)
                                if ts > 1e12:
                                    ts /= 1000.0
                                msg_time = datetime.fromtimestamp(ts)
                            else:
                                import re
                                from datetime import timezone, timedelta
                                normalized = re.sub(r"(\.\d{6})\d+", r"\1", str(raw_time))
                                parsed = datetime.fromisoformat(
                                    normalized.replace("Z", "+00:00")
                                )
                                # cfmail created_at is UTC without tz marker;
                                # treat naive timestamps as UTC and convert to local
                                if parsed.tzinfo is None:
                                    parsed = parsed.replace(tzinfo=timezone.utc)
                                msg_time = parsed.astimezone().replace(tzinfo=None)
                            if msg_time < since_time:
                                continue
                        except Exception:
                            pass

                # admin/mails returns `raw` (RFC822) directly in list
                raw_content = msg.get("raw") or ""
                content = self._extract_body_from_raw(raw_content)
                if not content and raw_content:
                    content = raw_content

                summary = (msg.get("subject") or "") + (msg.get("text") or "") + (msg.get("html") or "")
                searchable = content or summary
                if searchable:
                    code = extract_verification_code(searchable)
                    if code:
                        self._log("info", f"✅ 找到验证码: {code}")
                        return code
                    self._log("info", f"❌ 邮件 {idx} 中未找到验证码 (内容长度: {len(searchable)})")
                else:
                    self._log("warning", f"⚠️ 邮件 {idx} 无任何可解析内容")

            self._log("warning", "⚠️ 所有邮件中均未找到验证码")
            return None
        except Exception as exc:
            self._log("error", f"❌ 获取验证码异常: {exc}")
            return None

    def poll_for_code(
        self,
        timeout: int = 120,
        interval: int = 4,
        since_time: Optional[datetime] = None,
    ) -> Optional[str]:
        if not self.email:
            return None

        max_retries = max(1, timeout // interval)
        self._log("info", f"⏱️ 开始轮询验证码 (超时 {timeout}秒, 间隔 {interval}秒, 最多 {max_retries} 次)")
        for i in range(1, max_retries + 1):
            self._log("info", f"🔄 第 {i}/{max_retries} 次轮询...")
            code = self.fetch_verification_code(since_time=since_time)
            if code:
                self._log("info", f"🎉 验证码获取成功: {code}")
                return code
            if i < max_retries:
                self._log("info", f"⏳ 等待 {interval} 秒后重试...")
                time.sleep(interval)

        self._log("error", f"⏰ 验证码获取超时 ({timeout}秒)")
        return None
