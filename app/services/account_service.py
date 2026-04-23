from __future__ import annotations

import logging
import math
from typing import Any, Awaitable, Callable, Protocol


class AccountMutationDeps(Protocol):
    bulk_delete_accounts: Callable[..., tuple[Any, int, list[str]]]
    bulk_update_account_disabled_status: Callable[[list[str], bool, Any], tuple[int, list[str]]]
    delete_account: Callable[..., Any]
    get_global_stats: Callable[[], dict[str, Any]]
    get_http_client: Callable[[], Any]
    get_multi_account_mgr: Callable[[], Any]
    get_retry_policy: Callable[[], Any]
    get_session_cache_ttl_seconds: Callable[[], int]
    get_user_agent: Callable[[], str]
    logger: logging.Logger
    save_account_cooldown_state: Callable[[str, Any], Awaitable[Any]]
    set_multi_account_mgr: Callable[[Any], None]
    update_account_disabled_status: Callable[[str, bool, Any], Any]
    update_accounts_config: Callable[..., Any]


ACCOUNT_STATE_CODES = {
    "active",
    "manual_disabled",
    "access_restricted",
    "expired",
    "expiring_soon",
    "rate_limited",
    "quota_limited",
    "unavailable",
}


def _get_disabled_reason(account_manager: Any, account_config: Any) -> str | None:
    return (
        getattr(account_manager, "disabled_reason", None)
        or getattr(account_config, "disabled_reason", None)
    )


def build_account_state(
    account_manager: Any,
    status: str,
    remaining_hours: Any,
    cooldown_seconds: int,
    cooldown_reason: str | None,
    quota_status: dict[str, Any],
) -> dict[str, Any]:
    account_config = account_manager.config
    disabled_reason = _get_disabled_reason(account_manager, account_config)

    state = {
        "code": "active",
        "label": "Active",
        "severity": "success",
        "reason": None,
        "cooldown_seconds": cooldown_seconds,
        "can_enable": False,
        "can_disable": True,
        "can_delete": True,
    }

    if account_config.disabled:
        is_access_restricted = bool(disabled_reason and "403" in disabled_reason)
        state.update(
            {
                "code": "access_restricted" if is_access_restricted else "manual_disabled",
                "label": "Access restricted" if is_access_restricted else "Manual disabled",
                "severity": "danger" if is_access_restricted else "muted",
                "reason": disabled_reason,
                "can_enable": True,
                "can_disable": False,
            }
        )
        return state

    if account_config.is_expired():
        state.update(
            {
                "code": "expired",
                "label": "Expired",
                "severity": "danger",
                "reason": status,
                "can_disable": False,
            }
        )
        return state

    if cooldown_seconds > 0:
        state.update(
            {
                "code": "rate_limited",
                "label": "Rate limited",
                "severity": "warning",
                "reason": cooldown_reason,
                "can_enable": True,
            }
        )
        return state

    if quota_status.get("limited_count", 0) > 0:
        state.update(
            {
                "code": "quota_limited",
                "label": "Quota limited",
                "severity": "warning",
                "reason": "quota_limited",
            }
        )
        return state

    if remaining_hours is not None and 0 < remaining_hours < 3:
        state.update(
            {
                "code": "expiring_soon",
                "label": "Expiring soon",
                "severity": "warning",
                "reason": status,
            }
        )
        return state

    if not account_manager.is_available:
        state.update(
            {
                "code": "unavailable",
                "label": "Unavailable",
                "severity": "warning",
                "reason": status,
                "can_enable": True,
            }
        )
        return state

    return state


def build_account_entry(
    account_manager: Any,
    format_account_expiration: Callable[[Any], tuple[str, str, str]],
) -> dict[str, Any]:
    account_config = account_manager.config
    remaining_hours = account_config.get_remaining_hours()
    status, _status_color, remaining_display = format_account_expiration(remaining_hours)
    cooldown_seconds, cooldown_reason = account_manager.get_cooldown_info()
    quota_status = account_manager.get_quota_status()

    return {
        "id": account_config.account_id,
        "state": build_account_state(
            account_manager,
            status,
            remaining_hours,
            cooldown_seconds,
            cooldown_reason,
            quota_status,
        ),
        "status": status,
        "expires_at": account_config.expires_at or "未设置",
        "remaining_hours": remaining_hours,
        "remaining_display": remaining_display,
        "is_available": account_manager.is_available,
        "failure_count": account_manager.failure_count,
        "disabled": account_config.disabled,
        "disabled_reason": _get_disabled_reason(account_manager, account_config),
        "cooldown_seconds": cooldown_seconds,
        "cooldown_reason": cooldown_reason,
        "conversation_count": account_manager.conversation_count,
        "session_usage_count": account_manager.session_usage_count,
        "quota_status": quota_status,
        "trial_end": account_config.trial_end,
        "trial_days_remaining": account_config.get_trial_days_remaining(),
    }


def get_accounts_payload(
    multi_account_mgr: Any,
    format_account_expiration: Callable[[Any], tuple[str, str, str]],
    *,
    page: int = 1,
    page_size: int = 50,
    query: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    normalized_page = max(1, int(page))
    normalized_page_size = max(1, min(int(page_size), 200))
    raw_query = (query or "").strip()
    normalized_query = raw_query.lower()
    normalized_status = (status or "all").strip() or "all"

    if normalized_status != "all" and normalized_status not in ACCOUNT_STATE_CODES:
        raise ValueError(f"Unsupported account status filter: {normalized_status}")

    accounts: list[dict[str, Any]] = []
    for account_manager in multi_account_mgr.accounts.values():
        if normalized_query and normalized_query not in account_manager.config.account_id.lower():
            continue

        account_entry = build_account_entry(account_manager, format_account_expiration)
        if normalized_status != "all" and account_entry["state"]["code"] != normalized_status:
            continue

        accounts.append(account_entry)

    total = len(accounts)
    total_pages = max(1, math.ceil(total / normalized_page_size)) if total else 1
    current_page = min(normalized_page, total_pages)
    start = (current_page - 1) * normalized_page_size
    end = start + normalized_page_size

    return {
        "total": total,
        "page": current_page,
        "page_size": normalized_page_size,
        "total_pages": total_pages,
        "query": raw_query,
        "status": normalized_status,
        "accounts": accounts[start:end],
    }


def get_accounts_config_payload(load_accounts_from_source: Callable[[], list[Any]]) -> dict[str, Any]:
    return {"accounts": load_accounts_from_source()}


def update_accounts_config_payload(
    accounts_data: list[Any],
    deps: AccountMutationDeps,
) -> dict[str, Any]:
    multi_account_mgr = deps.update_accounts_config(
        accounts_data,
        deps.get_multi_account_mgr(),
        deps.get_http_client(),
        deps.get_user_agent(),
        deps.get_retry_policy(),
        deps.get_session_cache_ttl_seconds(),
        deps.get_global_stats(),
    )
    deps.set_multi_account_mgr(multi_account_mgr)
    return {
        "status": "success",
        "message": "配置已更新",
        "account_count": len(multi_account_mgr.accounts),
    }


def delete_account_payload(account_id: str, deps: AccountMutationDeps) -> dict[str, Any]:
    multi_account_mgr = deps.delete_account(
        account_id,
        deps.get_multi_account_mgr(),
        deps.get_http_client(),
        deps.get_user_agent(),
        deps.get_retry_policy(),
        deps.get_session_cache_ttl_seconds(),
        deps.get_global_stats(),
    )
    deps.set_multi_account_mgr(multi_account_mgr)
    return {
        "status": "success",
        "message": f"账户 {account_id} 已删除",
        "account_count": len(multi_account_mgr.accounts),
    }


def validate_bulk_delete_account_ids(account_ids: list[str], limit: int = 50) -> None:
    if len(account_ids) > limit:
        raise ValueError(f"单次最多删除 {limit} 个账户，当前请求 {len(account_ids)} 个")
    if not account_ids:
        raise ValueError("账户 ID 列表不能为空")


def bulk_delete_accounts_payload(
    account_ids: list[str],
    deps: AccountMutationDeps,
) -> dict[str, Any]:
    multi_account_mgr, success_count, errors = deps.bulk_delete_accounts(
        account_ids,
        deps.get_multi_account_mgr(),
        deps.get_http_client(),
        deps.get_user_agent(),
        deps.get_retry_policy(),
        deps.get_session_cache_ttl_seconds(),
        deps.get_global_stats(),
    )
    deps.set_multi_account_mgr(multi_account_mgr)
    return {"status": "success", "success_count": success_count, "errors": errors}


async def set_account_disabled_payload(
    account_id: str,
    disabled: bool,
    deps: AccountMutationDeps,
) -> dict[str, Any]:
    multi_account_mgr = deps.update_account_disabled_status(
        account_id,
        disabled,
        deps.get_multi_account_mgr(),
    )
    deps.set_multi_account_mgr(multi_account_mgr)

    if account_id in multi_account_mgr.accounts:
        account_mgr = multi_account_mgr.accounts[account_id]
        if not disabled:
            account_mgr.quota_cooldowns = {}
            deps.logger.info(f"[CONFIG] 账户 {account_id} 冷却状态已重置")
        await deps.save_account_cooldown_state(account_id, account_mgr)

    action_label = "禁用" if disabled else "启用"
    return {
        "status": "success",
        "message": f"账户 {account_id} 已{action_label}",
        "account_count": len(multi_account_mgr.accounts),
    }


def bulk_set_account_disabled_payload(
    account_ids: list[str],
    disabled: bool,
    deps: AccountMutationDeps,
) -> dict[str, Any]:
    multi_account_mgr = deps.get_multi_account_mgr()
    success_count, errors = deps.bulk_update_account_disabled_status(
        account_ids,
        disabled,
        multi_account_mgr,
    )
    if not disabled:
        for account_id in account_ids:
            if account_id in multi_account_mgr.accounts:
                multi_account_mgr.accounts[account_id].quota_cooldowns = {}
    return {"status": "success", "success_count": success_count, "errors": errors}
