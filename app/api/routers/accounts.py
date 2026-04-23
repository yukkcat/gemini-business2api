from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import Body, FastAPI, HTTPException, Query, Request

from app.services import (
    bulk_delete_accounts_payload,
    bulk_set_account_disabled_payload,
    delete_account_payload,
    get_accounts_config_payload,
    get_accounts_payload,
    set_account_disabled_payload,
    update_accounts_config_payload,
    validate_bulk_delete_account_ids,
)


@dataclass(frozen=True)
class AccountRouteDeps:
    bulk_delete_accounts: Callable[..., tuple[Any, int, list[str]]]
    bulk_update_account_disabled_status: Callable[[list[str], bool, Any], tuple[int, list[str]]]
    delete_account: Callable[..., Any]
    format_account_expiration: Callable[[Any], tuple[str, str, str]]
    get_global_stats: Callable[[], dict[str, Any]]
    get_http_client: Callable[[], Any]
    get_multi_account_mgr: Callable[[], Any]
    get_retry_policy: Callable[[], Any]
    get_session_cache_ttl_seconds: Callable[[], int]
    get_user_agent: Callable[[], str]
    load_accounts_from_source: Callable[[], list[Any]]
    logger: logging.Logger
    require_login: Callable[..., Callable]
    save_account_cooldown_state: Callable[[str, Any], Awaitable[Any]]
    set_multi_account_mgr: Callable[[Any], None]
    update_account_disabled_status: Callable[[str, bool, Any], Any]
    update_accounts_config: Callable[..., Any]


def register_account_routes(app: FastAPI, deps: AccountRouteDeps) -> None:
    @app.get("/admin/accounts")
    @deps.require_login()
    async def admin_get_accounts(
        request: Request,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        query: str | None = Query(None),
        status: str = Query("all"),
    ):
        try:
            return get_accounts_payload(
                deps.get_multi_account_mgr(),
                deps.format_account_expiration,
                page=page,
                page_size=page_size,
                query=query,
                status=status,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/admin/accounts-config")
    @deps.require_login()
    async def admin_get_config(request: Request):
        try:
            return get_accounts_config_payload(deps.load_accounts_from_source)
        except Exception as exc:
            deps.logger.error(f"[CONFIG] 获取账户配置失败: {str(exc)}")
            raise HTTPException(500, f"获取失败: {str(exc)}") from exc

    @app.put("/admin/accounts-config")
    @deps.require_login()
    async def admin_update_config(request: Request, accounts_data: list[Any] = Body(...)):
        try:
            return update_accounts_config_payload(accounts_data, deps)
        except Exception as exc:
            deps.logger.error(f"[CONFIG] 更新账户配置失败: {str(exc)}")
            raise HTTPException(500, f"更新失败: {str(exc)}") from exc

    @app.delete("/admin/accounts/{account_id}")
    @deps.require_login()
    async def admin_delete_account(request: Request, account_id: str):
        try:
            return delete_account_payload(account_id, deps)
        except Exception as exc:
            deps.logger.error(f"[CONFIG] 删除账户失败: {str(exc)}")
            raise HTTPException(500, f"删除失败: {str(exc)}") from exc

    @app.put("/admin/accounts/bulk-delete")
    @deps.require_login()
    async def admin_bulk_delete_accounts(request: Request, account_ids: list[str] = Body(...)):
        try:
            validate_bulk_delete_account_ids(account_ids)
            return bulk_delete_accounts_payload(account_ids, deps)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            deps.logger.error(f"[CONFIG] 批量删除账户失败: {str(exc)}")
            raise HTTPException(500, f"删除失败: {str(exc)}") from exc

    @app.put("/admin/accounts/{account_id}/disable")
    @deps.require_login()
    async def admin_disable_account(request: Request, account_id: str):
        try:
            return await set_account_disabled_payload(account_id, True, deps)
        except Exception as exc:
            deps.logger.error(f"[CONFIG] 禁用账户失败: {str(exc)}")
            raise HTTPException(500, f"禁用失败: {str(exc)}") from exc

    @app.put("/admin/accounts/{account_id}/enable")
    @deps.require_login()
    async def admin_enable_account(request: Request, account_id: str):
        try:
            return await set_account_disabled_payload(account_id, False, deps)
        except Exception as exc:
            deps.logger.error(f"[CONFIG] 启用账户失败: {str(exc)}")
            raise HTTPException(500, f"启用失败: {str(exc)}") from exc

    @app.put("/admin/accounts/bulk-enable")
    @deps.require_login()
    async def admin_bulk_enable_accounts(request: Request, account_ids: list[str] = Body(...)):
        return bulk_set_account_disabled_payload(account_ids, False, deps)

    @app.put("/admin/accounts/bulk-disable")
    @deps.require_login()
    async def admin_bulk_disable_accounts(request: Request, account_ids: list[str] = Body(...)):
        return bulk_set_account_disabled_payload(account_ids, True, deps)
