from __future__ import annotations

import asyncio
import json
import ssl
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, AsyncIterable, Awaitable, Callable

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.services.chat_media_service import ChatMediaFollowupDeps, execute_generated_media_followups


def build_openai_model_ids(
    model_mapping: dict[str, Any],
    extra_model_ids: tuple[str, ...] = ("gemini-imagen", "gemini-veo"),
) -> list[str]:
    return [*model_mapping.keys(), *extra_model_ids]


def resolve_request_client_ip(request: Any) -> str:
    client_ip = request.headers.get("x-forwarded-for")
    if client_ip:
        return client_ip.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def build_model_not_found_error(
    *,
    model: str,
    model_mapping: dict[str, Any],
    virtual_models: dict[str, Any],
) -> HTTPException | None:
    if model in model_mapping or model in virtual_models:
        return None

    all_models = [*model_mapping.keys(), *virtual_models.keys()]
    return HTTPException(
        status_code=404,
        detail=f"Model '{model}' not found. Available models: {all_models}",
    )


def create_chat_completion_chunk(
    *,
    chunk_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None,
) -> str:
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "logprobs": None,
                "finish_reason": finish_reason,
            }
        ],
        "system_fingerprint": None,
    }
    return json.dumps(chunk)


def build_last_message_preview(messages: list[Any]) -> str:
    if not messages:
        return "[空消息]"

    last_content = messages[-1].content
    if isinstance(last_content, str):
        return last_content[:500] + "...(已截断)" if len(last_content) > 500 else last_content
    return f"[多模态: {len(last_content)}部分]"


@dataclass(frozen=True)
class ChatMetricsDeps:
    build_recent_conversation_entry: Callable[..., dict[str, Any]]
    global_stats: dict[str, Any]
    multi_account_mgr: Any
    save_stats: Callable[[dict[str, Any]], Awaitable[None]]
    stats_db: Any
    stats_lock: Any
    uptime_tracker: Any


@dataclass(frozen=True)
class ChatRequestPrelude:
    client_ip: str
    conversation_key: str
    required_quota_types: list[str]


@dataclass(frozen=True)
class ChatSessionResolution:
    account_manager: Any
    google_session: str
    is_new_conversation: bool


@dataclass(frozen=True)
class ChatSessionResolveDeps:
    classify_error_status: Callable[[int | None, Exception], str]
    create_google_session: Callable[[Any, Any, str, str], Awaitable[str]]
    finalize_result: Callable[[str, int | None, str | None], Awaitable[None]]
    http_client: Any
    logger: Any
    max_account_switch_tries: int
    multi_account_mgr: Any
    request: Any
    uptime_tracker: Any
    user_agent: str


@dataclass(frozen=True)
class ChatRetryPreparation:
    file_ids: list[str]
    retry_mode: bool
    session_id: str
    text_content: str


@dataclass(frozen=True)
class ChatRetryPreparationDeps:
    build_full_context_text: Callable[[list[Any]], str]
    create_google_session: Callable[[Any, Any, str, str], Awaitable[str]]
    http_client: Any
    logger: Any
    multi_account_mgr: Any
    upload_context_file: Callable[..., Awaitable[str]]
    user_agent: str


@dataclass(frozen=True)
class ChatRetryFailover:
    account_manager: Any
    file_ids: list[str]
    retry_mode: bool


@dataclass(frozen=True)
class ChatRetryFailoverDeps:
    create_google_session: Callable[[Any, Any, str, str], Awaitable[str]]
    http_client: Any
    logger: Any
    multi_account_mgr: Any
    request: Any
    user_agent: str


@dataclass(frozen=True)
class ChatRetryErrorOutcome:
    error_detail: str
    should_retry: bool
    status: str
    status_code: int | None
    stream_error_message: str | None = None


@dataclass(frozen=True)
class ChatRetryErrorDeps:
    classify_error_status: Callable[[int | None, Exception], str]
    get_request_quota_type: Callable[[str], str]
    logger: Any
    uptime_tracker: Any


@dataclass(frozen=True)
class ChatRetryFailoverErrorDeps:
    classify_error_status: Callable[[int | None, Exception], str]
    finalize_result: Callable[[str, int | None, str | None], Awaitable[None]]
    logger: Any
    uptime_tracker: Any


@dataclass(frozen=True)
class ChatResponseRetryDeps:
    finalize_result: Callable[[str, int | None, str | None], Awaitable[None]]
    max_account_switch_tries: int
    multi_account_mgr: Any
    prepare_retry_deps: ChatRetryPreparationDeps
    retry_error_deps: ChatRetryErrorDeps
    retry_failover_deps: ChatRetryFailoverDeps
    retry_failover_error_deps: ChatRetryFailoverErrorDeps
    stream_chat: Callable[..., AsyncIterable[str]]
    uptime_tracker: Any


@dataclass(frozen=True)
class ChatResponseRetryContext:
    chat_id: str
    conversation_key: str
    created_time: int
    current_images: list[Any]
    initial_retry_mode: bool
    initial_text: str
    messages: list[Any]
    model: str
    request: Any
    request_id: str
    required_quota_types: list[str]
    stream: bool


@dataclass(frozen=True)
class ChatResponseExecutionSetupDeps:
    build_full_context_text: Callable[[list[Any]], str]
    classify_error_status: Callable[[int | None, Exception], str]
    create_google_session: Callable[[Any, Any, str, str], Awaitable[str]]
    finalize_result: Callable[[str, int | None, str | None], Awaitable[None]]
    get_request_quota_type: Callable[[str], str]
    http_client: Any
    logger: Any
    max_account_switch_tries: int
    multi_account_mgr: Any
    parse_last_message: Callable[[list[Any], Any, str], Awaitable[tuple[str, list[Any]]]]
    request: Any
    stream_chat: Callable[..., AsyncIterable[str]]
    upload_context_file: Callable[..., Awaitable[str]]
    uptime_tracker: Any
    user_agent: str


@dataclass(frozen=True)
class ChatResponseExecutionPlan:
    chat_id: str
    created_time: int
    retry_context: ChatResponseRetryContext
    retry_deps: ChatResponseRetryDeps


@dataclass(frozen=True)
class ChatRequestHandlerDeps:
    build_full_context_text: Callable[[list[Any]], str]
    build_recent_conversation_entry: Callable[..., dict[str, Any]]
    create_google_session: Callable[[Any, Any, str, str], Awaitable[str]]
    get_conversation_key: Callable[[list[dict[str, Any]], str], str]
    get_required_quota_types: Callable[[str], list[str]]
    get_request_quota_type: Callable[[str], str]
    global_stats: dict[str, Any]
    http_client: Any
    logger: Any
    max_account_switch_tries: int
    model_mapping: dict[str, Any]
    multi_account_mgr: Any
    parse_last_message: Callable[[list[Any], Any, str], Awaitable[tuple[str, list[Any]]]]
    save_stats: Callable[[dict[str, Any]], Awaitable[None]]
    stats_db: Any
    stats_lock: Any
    stream_chat: Callable[..., AsyncIterable[str]]
    upload_context_file: Callable[..., Awaitable[str]]
    uptime_tracker: Any
    user_agent: str
    virtual_models: dict[str, Any]


@dataclass
class ChatStreamRuntimeState:
    file_ids_info: tuple[list[dict[str, str]], str] | None = None
    first_response_time: float | None = None
    full_content: str = ""
    json_objects: list[dict[str, Any]] = field(default_factory=list)
    response_count: int = 0
    usage_counted: bool = False


@dataclass(frozen=True)
class ChatStreamConsumeDeps:
    account_manager: Any
    create_chunk: Callable[[str, int, str, dict[str, Any], str | None], str]
    get_request_quota_type: Callable[[str], str]
    logger: Any
    parse_generated_media_files: Callable[[list[dict[str, Any]], Any], tuple[list[dict[str, str]], str]]
    request: Any


@dataclass(frozen=True)
class ChatStreamRequestSetup:
    headers: dict[str, str]
    payload: dict[str, Any]


@dataclass(frozen=True)
class ChatStreamRequestSetupDeps:
    account_manager: Any
    get_common_headers: Callable[[str, str], dict[str, str]]
    get_tools_spec: Callable[[str], dict[str, Any]]
    model_mapping: dict[str, Any]
    user_agent: str


@dataclass(frozen=True)
class ChatStreamExecuteDeps:
    consume_deps: ChatStreamConsumeDeps
    http_client: Any
    logger: Any
    parse_json_array_stream: Callable[[AsyncIterable[str]], AsyncIterable[dict[str, Any]]]
    stream_timeout: httpx.Timeout
    stream_url: str
    uptime_tracker: Any


@dataclass(frozen=True)
class ChatStreamPipelineDeps:
    account_manager: Any
    create_chunk: Callable[[str, int, str, dict[str, Any], str | None], str]
    get_common_headers: Callable[[str, str], dict[str, str]]
    get_request_quota_type: Callable[[str], str]
    get_tools_spec: Callable[[str], dict[str, Any]]
    http_client: Any
    logger: Any
    model_mapping: dict[str, Any]
    parse_generated_media_files: Callable[[list[dict[str, Any]], Any], tuple[list[dict[str, str]], str]]
    parse_json_array_stream: Callable[[AsyncIterable[str]], AsyncIterable[dict[str, Any]]]
    request: Any
    stream_timeout: httpx.Timeout
    stream_url: str
    uptime_tracker: Any
    user_agent: str


@dataclass(frozen=True)
class ChatStreamFinalizeDeps:
    account_manager: Any
    create_chunk: Callable[[str, int, str, dict[str, Any], str | None], str]
    get_request_quota_type: Callable[[str], str]
    logger: Any
    uptime_tracker: Any


@dataclass(frozen=True)
class ChatStreamFlowDeps:
    finalize_deps: ChatStreamFinalizeDeps
    media_followup_deps: ChatMediaFollowupDeps
    pipeline_deps: ChatStreamPipelineDeps


@dataclass(frozen=True)
class ChatStreamFlowSetupDeps:
    create_chunk: Callable[[str, int, str, dict[str, Any], str | None], str]
    download_media_file: Callable[..., Awaitable[bytes]]
    get_base_url: Callable[[Any], str]
    get_common_headers: Callable[[str, str], dict[str, str]]
    get_file_metadata: Callable[..., Awaitable[dict[str, Any]]]
    get_request_quota_type: Callable[[str], str]
    get_tools_spec: Callable[[str], dict[str, Any]]
    http_client: Any
    http_client_chat: Any
    image_dir: str
    image_output_format: str
    logger: Any
    model_mapping: dict[str, Any]
    parse_generated_media_files: Callable[[list[dict[str, Any]], Any], tuple[list[dict[str, str]], str]]
    parse_json_array_stream: Callable[[AsyncIterable[str]], AsyncIterable[dict[str, Any]]]
    request: Any
    save_media_file: Callable[..., str]
    stream_timeout: httpx.Timeout
    stream_url: str
    uptime_tracker: Any
    user_agent: str
    video_dir: str
    video_output_format: str


@dataclass(frozen=True)
class ChatStreamFlowStaticDeps:
    create_chunk: Callable[[str, int, str, dict[str, Any], str | None], str]
    download_media_file: Callable[..., Awaitable[bytes]]
    get_base_url: Callable[[Any], str]
    get_common_headers: Callable[[str, str], dict[str, str]]
    get_file_metadata: Callable[..., Awaitable[dict[str, Any]]]
    get_request_quota_type: Callable[[str], str]
    get_tools_spec: Callable[[str], dict[str, Any]]
    http_client: Any
    http_client_chat: Any
    image_dir: str
    image_output_format: str
    logger: Any
    model_mapping: dict[str, Any]
    parse_generated_media_files: Callable[[list[dict[str, Any]], Any], tuple[list[dict[str, str]], str]]
    parse_json_array_stream: Callable[[AsyncIterable[str]], AsyncIterable[dict[str, Any]]]
    save_media_file: Callable[..., str]
    stream_timeout: httpx.Timeout
    stream_url: str
    uptime_tracker: Any
    user_agent: str
    video_dir: str
    video_output_format: str


def classify_chat_error_status(status_code: int | None, error: Exception) -> str:
    if status_code == 504:
        return "timeout"
    if isinstance(error, (asyncio.TimeoutError, httpx.TimeoutException)):
        return "timeout"
    return "error"


def build_chat_request_prelude(
    *,
    request: Any,
    req: Any,
    get_required_quota_types: Callable[[str], list[str]],
    get_conversation_key: Callable[[list[dict[str, Any]], str], str],
) -> ChatRequestPrelude:
    client_ip = resolve_request_client_ip(request)
    request.state.model = req.model
    required_quota_types = get_required_quota_types(req.model)
    conversation_key = get_conversation_key([message.model_dump() for message in req.messages], client_ip)
    return ChatRequestPrelude(
        client_ip=client_ip,
        conversation_key=conversation_key,
        required_quota_types=required_quota_types,
    )


async def resolve_chat_session(
    *,
    deps: ChatSessionResolveDeps,
    request_id: str,
    required_quota_types: list[str],
    conversation_key: str,
) -> ChatSessionResolution:
    account_manager = None
    google_session = ""
    is_new_conversation = False

    session_lock = await deps.multi_account_mgr.acquire_session_lock(conversation_key)
    async with session_lock:
        cached_session = deps.multi_account_mgr.global_session_cache.get(conversation_key)

        if cached_session:
            account_id = cached_session["account_id"]
            try:
                account_manager = await deps.multi_account_mgr.get_account(
                    account_id,
                    request_id,
                    required_quota_types,
                )
                google_session = cached_session["session_id"]
                deps.request.state.last_account_id = account_manager.config.account_id
                deps.logger.info(
                    f"[CHAT] [{account_id}] [req_{request_id}] 继续会话: {google_session[-12:]}"
                )
            except HTTPException as exc:
                deps.logger.warning(
                    f"[CHAT] [req_{request_id}] 缓存会话账户不可用，切换新账户: {account_id} ({str(exc.detail)})"
                )
                deps.multi_account_mgr.global_session_cache.pop(conversation_key, None)
                cached_session = None

        if not cached_session:
            available_accounts = deps.multi_account_mgr.get_available_accounts(required_quota_types)
            max_retries = min(deps.max_account_switch_tries, len(available_accounts))
            last_error = None

            for retry_idx in range(max_retries):
                selected_account = None
                try:
                    selected_account = await deps.multi_account_mgr.get_account(
                        None,
                        request_id,
                        required_quota_types,
                    )
                    google_session = await deps.create_google_session(
                        selected_account,
                        deps.http_client,
                        deps.user_agent,
                        request_id,
                    )
                    await deps.multi_account_mgr.set_session_cache(
                        conversation_key,
                        selected_account.config.account_id,
                        google_session,
                    )
                    account_manager = selected_account
                    is_new_conversation = True
                    deps.request.state.last_account_id = account_manager.config.account_id
                    deps.logger.info(
                        f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 新会话创建并绑定账户"
                    )
                    deps.uptime_tracker.record_request("account_pool", True)
                    break
                except Exception as exc:
                    last_error = exc
                    status_code = exc.status_code if isinstance(exc, HTTPException) else None
                    account_id = selected_account.config.account_id if selected_account else "unknown"
                    deps.logger.error(
                        f"[CHAT] [req_{request_id}] 账户 {account_id} 创建会话失败 "
                        f"(尝试 {retry_idx + 1}/{max_retries}) - {type(exc).__name__}: {str(exc)}"
                    )
                    deps.uptime_tracker.record_request("account_pool", False, status_code=status_code)

                    if retry_idx == max_retries - 1:
                        deps.logger.error(f"[CHAT] [req_{request_id}] 所有账户均不可用")
                        status = deps.classify_error_status(
                            503,
                            last_error if isinstance(last_error, Exception) else Exception("account_pool_unavailable"),
                        )
                        await deps.finalize_result(
                            status,
                            503,
                            f"All accounts unavailable: {str(last_error)[:100]}",
                        )
                        raise HTTPException(503, f"All accounts unavailable: {str(last_error)[:100]}")

    if account_manager is None:
        deps.logger.error(f"[CHAT] [req_{request_id}] 无可用账户")
        await deps.finalize_result("error", 503, "No available accounts")
        raise HTTPException(503, "No available accounts")

    return ChatSessionResolution(
        account_manager=account_manager,
        google_session=google_session,
        is_new_conversation=is_new_conversation,
    )


async def prepare_chat_retry_attempt(
    *,
    deps: ChatRetryPreparationDeps,
    account_manager: Any,
    base_text: str,
    conversation_key: str,
    current_file_ids: list[str],
    current_images: list[Any],
    current_retry_mode: bool,
    messages: list[Any],
    request_id: str,
) -> ChatRetryPreparation:
    cached = deps.multi_account_mgr.global_session_cache.get(conversation_key)
    file_ids = list(current_file_ids)
    retry_mode = current_retry_mode

    if not cached:
        deps.logger.warning(
            f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 缓存已清理，重建Session"
        )
        session_id = await deps.create_google_session(
            account_manager,
            deps.http_client,
            deps.user_agent,
            request_id,
        )
        await deps.multi_account_mgr.set_session_cache(
            conversation_key,
            account_manager.config.account_id,
            session_id,
        )
        retry_mode = True
        file_ids = []
    else:
        session_id = cached["session_id"]

    if current_images and not file_ids:
        for image in current_images:
            file_id = await deps.upload_context_file(
                session_id,
                image["mime"],
                image["data"],
                account_manager,
                deps.http_client,
                deps.user_agent,
                request_id,
            )
            file_ids.append(file_id)

    text_content = deps.build_full_context_text(messages) if retry_mode else base_text
    return ChatRetryPreparation(
        file_ids=file_ids,
        retry_mode=retry_mode,
        session_id=session_id,
        text_content=text_content,
    )


async def prepare_chat_response_execution(
    *,
    deps: ChatResponseExecutionSetupDeps,
    account_manager: Any,
    conversation_key: str,
    is_new_conversation: bool,
    messages: list[Any],
    model: str,
    request_id: str,
    required_quota_types: list[str],
    stream: bool,
) -> ChatResponseExecutionPlan:
    preview = build_last_message_preview(messages)
    deps.logger.info(
        f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 收到请求: "
        f"{model} | {len(messages)}条消息 | stream={stream}"
    )
    deps.logger.info(
        f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 用户消息: {preview}"
    )

    try:
        last_text, current_images = await deps.parse_last_message(messages, deps.http_client, request_id)
    except HTTPException as exc:
        status = deps.classify_error_status(exc.status_code, exc)
        await deps.finalize_result(status, exc.status_code, f"HTTP {exc.status_code}: {exc.detail}")
        raise
    except Exception as exc:
        status = deps.classify_error_status(None, exc)
        await deps.finalize_result(status, 500, f"{type(exc).__name__}: {str(exc)[:200]}")
        raise

    text_to_send = last_text
    is_retry_mode = is_new_conversation
    if not is_new_conversation:
        await deps.multi_account_mgr.update_session_time(conversation_key)

    chat_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    retry_deps = ChatResponseRetryDeps(
        finalize_result=deps.finalize_result,
        max_account_switch_tries=deps.max_account_switch_tries,
        multi_account_mgr=deps.multi_account_mgr,
        prepare_retry_deps=ChatRetryPreparationDeps(
            build_full_context_text=deps.build_full_context_text,
            create_google_session=deps.create_google_session,
            http_client=deps.http_client,
            logger=deps.logger,
            multi_account_mgr=deps.multi_account_mgr,
            upload_context_file=deps.upload_context_file,
            user_agent=deps.user_agent,
        ),
        retry_error_deps=ChatRetryErrorDeps(
            classify_error_status=deps.classify_error_status,
            get_request_quota_type=deps.get_request_quota_type,
            logger=deps.logger,
            uptime_tracker=deps.uptime_tracker,
        ),
        retry_failover_deps=ChatRetryFailoverDeps(
            create_google_session=deps.create_google_session,
            http_client=deps.http_client,
            logger=deps.logger,
            multi_account_mgr=deps.multi_account_mgr,
            request=deps.request,
            user_agent=deps.user_agent,
        ),
        retry_failover_error_deps=ChatRetryFailoverErrorDeps(
            classify_error_status=deps.classify_error_status,
            finalize_result=deps.finalize_result,
            logger=deps.logger,
            uptime_tracker=deps.uptime_tracker,
        ),
        stream_chat=deps.stream_chat,
        uptime_tracker=deps.uptime_tracker,
    )
    retry_context = ChatResponseRetryContext(
        chat_id=chat_id,
        conversation_key=conversation_key,
        created_time=created_time,
        current_images=current_images,
        initial_retry_mode=is_retry_mode,
        initial_text=text_to_send,
        messages=messages,
        model=model,
        request=deps.request,
        request_id=request_id,
        required_quota_types=required_quota_types,
        stream=stream,
    )
    return ChatResponseExecutionPlan(
        chat_id=chat_id,
        created_time=created_time,
        retry_context=retry_context,
        retry_deps=retry_deps,
    )


async def failover_chat_retry_account(
    *,
    deps: ChatRetryFailoverDeps,
    account_manager: Any,
    conversation_key: str,
    request_id: str,
    required_quota_types: list[str],
) -> ChatRetryFailover:
    new_account = await deps.multi_account_mgr.get_account(
        None,
        request_id,
        required_quota_types,
    )
    deps.logger.info(
        f"[CHAT] [req_{request_id}] 切换账户: {account_manager.config.account_id} -> {new_account.config.account_id}"
    )

    session_id = await deps.create_google_session(
        new_account,
        deps.http_client,
        deps.user_agent,
        request_id,
    )
    await deps.multi_account_mgr.set_session_cache(
        conversation_key,
        new_account.config.account_id,
        session_id,
    )
    deps.request.state.last_account_id = new_account.config.account_id

    return ChatRetryFailover(
        account_manager=new_account,
        file_ids=[],
        retry_mode=True,
    )


async def prepare_chat_stream_request(
    *,
    deps: ChatStreamRequestSetupDeps,
    file_ids: list[str],
    model_name: str,
    request_id: str,
    session: str,
    text_content: str,
) -> ChatStreamRequestSetup:
    jwt = await deps.account_manager.get_jwt(request_id)
    headers = deps.get_common_headers(jwt, deps.user_agent)
    payload = {
        "configId": deps.account_manager.config.config_id,
        "additionalParams": {"token": "-"},
        "streamAssistRequest": {
            "session": session,
            "query": {"parts": [{"text": text_content}]},
            "filter": "",
            "fileIds": file_ids,
            "answerGenerationMode": "NORMAL",
            "toolsSpec": deps.get_tools_spec(model_name),
            "languageCode": "zh-CN",
            "userMetadata": {"timeZone": "Asia/Shanghai"},
            "assistSkippingMode": "REQUEST_ASSIST",
        },
    }

    target_model_id = deps.model_mapping.get(model_name)
    if target_model_id:
        payload["streamAssistRequest"]["assistGenerationConfig"] = {
            "modelId": target_model_id,
        }

    return ChatStreamRequestSetup(headers=headers, payload=payload)


async def run_chat_stream_pipeline(
    *,
    deps: ChatStreamPipelineDeps,
    state: ChatStreamRuntimeState,
    session: str,
    text_content: str,
    file_ids: list[str],
    model_name: str,
    chat_id: str,
    created_time: int,
    request_id: str,
    is_stream: bool,
) -> AsyncIterable[str]:
    text_preview = text_content[:500] + "...(已截断)" if len(text_content) > 500 else text_content
    deps.logger.info(
        f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] 发送内容: {text_preview}"
    )
    if file_ids:
        deps.logger.info(
            f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] 附带文件: {len(file_ids)}个"
        )

    stream_request = await prepare_chat_stream_request(
        deps=ChatStreamRequestSetupDeps(
            account_manager=deps.account_manager,
            get_common_headers=deps.get_common_headers,
            get_tools_spec=deps.get_tools_spec,
            model_mapping=deps.model_mapping,
            user_agent=deps.user_agent,
        ),
        file_ids=file_ids,
        model_name=model_name,
        request_id=request_id,
        session=session,
        text_content=text_content,
    )

    if is_stream:
        chunk = deps.create_chunk(chat_id, created_time, model_name, {"role": "assistant"}, None)
        yield f"data: {chunk}\n\n"

    stream_execute_deps = ChatStreamExecuteDeps(
        consume_deps=ChatStreamConsumeDeps(
            account_manager=deps.account_manager,
            create_chunk=deps.create_chunk,
            get_request_quota_type=deps.get_request_quota_type,
            logger=deps.logger,
            parse_generated_media_files=deps.parse_generated_media_files,
            request=deps.request,
        ),
        http_client=deps.http_client,
        logger=deps.logger,
        parse_json_array_stream=deps.parse_json_array_stream,
        stream_timeout=deps.stream_timeout,
        stream_url=deps.stream_url,
        uptime_tracker=deps.uptime_tracker,
    )

    async for chunk in execute_chat_stream_request(
        deps=stream_execute_deps,
        state=state,
        stream_request=stream_request,
        chat_id=chat_id,
        created_time=created_time,
        model_name=model_name,
        request_id=request_id,
    ):
        yield chunk


def build_chat_stream_flow_deps(
    *,
    deps: ChatStreamFlowSetupDeps,
    account_manager: Any,
) -> ChatStreamFlowDeps:
    return ChatStreamFlowDeps(
        finalize_deps=ChatStreamFinalizeDeps(
            account_manager=account_manager,
            create_chunk=deps.create_chunk,
            get_request_quota_type=deps.get_request_quota_type,
            logger=deps.logger,
            uptime_tracker=deps.uptime_tracker,
        ),
        media_followup_deps=ChatMediaFollowupDeps(
            account_manager=account_manager,
            create_chunk=deps.create_chunk,
            download_media_file=deps.download_media_file,
            get_base_url=deps.get_base_url,
            get_file_metadata=deps.get_file_metadata,
            http_client=deps.http_client,
            image_dir=deps.image_dir,
            image_output_format=deps.image_output_format,
            logger=deps.logger,
            request=deps.request,
            save_media_file=deps.save_media_file,
            user_agent=deps.user_agent,
            video_dir=deps.video_dir,
            video_output_format=deps.video_output_format,
        ),
        pipeline_deps=ChatStreamPipelineDeps(
            account_manager=account_manager,
            create_chunk=deps.create_chunk,
            get_common_headers=deps.get_common_headers,
            get_request_quota_type=deps.get_request_quota_type,
            get_tools_spec=deps.get_tools_spec,
            http_client=deps.http_client_chat,
            logger=deps.logger,
            model_mapping=deps.model_mapping,
            parse_generated_media_files=deps.parse_generated_media_files,
            parse_json_array_stream=deps.parse_json_array_stream,
            request=deps.request,
            stream_timeout=deps.stream_timeout,
            stream_url=deps.stream_url,
            uptime_tracker=deps.uptime_tracker,
            user_agent=deps.user_agent,
        ),
    )


def build_chat_stream_flow_setup_deps(
    *,
    deps: ChatStreamFlowStaticDeps,
    request: Any,
) -> ChatStreamFlowSetupDeps:
    return ChatStreamFlowSetupDeps(
        create_chunk=deps.create_chunk,
        download_media_file=deps.download_media_file,
        get_base_url=deps.get_base_url,
        get_common_headers=deps.get_common_headers,
        get_file_metadata=deps.get_file_metadata,
        get_request_quota_type=deps.get_request_quota_type,
        get_tools_spec=deps.get_tools_spec,
        http_client=deps.http_client,
        http_client_chat=deps.http_client_chat,
        image_dir=deps.image_dir,
        image_output_format=deps.image_output_format,
        logger=deps.logger,
        model_mapping=deps.model_mapping,
        parse_generated_media_files=deps.parse_generated_media_files,
        parse_json_array_stream=deps.parse_json_array_stream,
        request=request,
        save_media_file=deps.save_media_file,
        stream_timeout=deps.stream_timeout,
        stream_url=deps.stream_url,
        uptime_tracker=deps.uptime_tracker,
        user_agent=deps.user_agent,
        video_dir=deps.video_dir,
        video_output_format=deps.video_output_format,
    )


async def run_chat_stream_flow(
    *,
    deps: ChatStreamFlowDeps,
    session: str,
    text_content: str,
    file_ids: list[str],
    model_name: str,
    chat_id: str,
    created_time: int,
    request_id: str,
    is_stream: bool,
) -> AsyncIterable[str]:
    start_time = time.time()
    state = ChatStreamRuntimeState()

    async for chunk in run_chat_stream_pipeline(
        deps=deps.pipeline_deps,
        state=state,
        session=session,
        text_content=text_content,
        file_ids=file_ids,
        model_name=model_name,
        chat_id=chat_id,
        created_time=created_time,
        request_id=request_id,
        is_stream=is_stream,
    ):
        yield chunk

    if state.file_ids_info:
        media_followup = await execute_generated_media_followups(
            deps=deps.media_followup_deps,
            file_ids_info=state.file_ids_info,
            chat_id=chat_id,
            created_time=created_time,
            model_name=model_name,
            request_id=request_id,
        )
        if media_followup.first_response_time is not None and state.first_response_time is None:
            state.first_response_time = media_followup.first_response_time
        for media_chunk in media_followup.chunks:
            yield media_chunk
        state.file_ids_info = None

    for final_chunk in finalize_chat_stream_response(
        deps=deps.finalize_deps,
        state=state,
        start_time=start_time,
        chat_id=chat_id,
        created_time=created_time,
        model_name=model_name,
        request_id=request_id,
        is_stream=is_stream,
    ):
        yield final_chunk


async def stream_chat_with_flow(
    *,
    deps: ChatStreamFlowStaticDeps,
    request: Any,
    account_manager: Any,
    session: str,
    text_content: str,
    file_ids: list[str],
    model_name: str,
    chat_id: str,
    created_time: int,
    is_stream: bool = True,
    request_id: str = "",
) -> AsyncIterable[str]:
    async for chunk in run_chat_stream_flow(
        deps=build_chat_stream_flow_deps(
            deps=build_chat_stream_flow_setup_deps(deps=deps, request=request),
            account_manager=account_manager,
        ),
        session=session,
        text_content=text_content,
        file_ids=file_ids,
        model_name=model_name,
        chat_id=chat_id,
        created_time=created_time,
        request_id=request_id,
        is_stream=is_stream,
    ):
        yield chunk


async def execute_chat_stream_request(
    *,
    deps: ChatStreamExecuteDeps,
    state: ChatStreamRuntimeState,
    stream_request: ChatStreamRequestSetup,
    chat_id: str,
    created_time: int,
    model_name: str,
    request_id: str,
) -> AsyncIterable[str]:
    async with deps.http_client.stream(
        "POST",
        deps.stream_url,
        headers=stream_request.headers,
        json=stream_request.payload,
        timeout=deps.stream_timeout,
    ) as response:
        if response.status_code != 200:
            error_text = await response.aread()
            deps.uptime_tracker.record_request(model_name, False, status_code=response.status_code)
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Upstream Error {error_text.decode()}",
            )

        try:
            async for chunk in consume_chat_stream_responses(
                deps=deps.consume_deps,
                state=state,
                json_stream=deps.parse_json_array_stream(response.aiter_lines()),
                chat_id=chat_id,
                created_time=created_time,
                model_name=model_name,
                request_id=request_id,
            ):
                yield chunk
        except ValueError as exc:
            deps.uptime_tracker.record_request(model_name, False)
            deps.logger.error(
                f"[API] [{deps.consume_deps.account_manager.config.account_id}] [req_{request_id}] "
                f"JSON解析失败: {str(exc)}"
            )
        except Exception as exc:
            error_type = type(exc).__name__
            deps.uptime_tracker.record_request(model_name, False)
            deps.logger.error(
                f"[API] [{deps.consume_deps.account_manager.config.account_id}] [req_{request_id}] "
                f"流处理错误 ({error_type}): {str(exc)}"
            )
            raise


def _mark_stream_first_response(
    *,
    request: Any,
    state: ChatStreamRuntimeState,
) -> None:
    if state.first_response_time is None:
        state.first_response_time = time.time()
        if request is not None:
            request.state.first_response_time = state.first_response_time


async def consume_chat_stream_responses(
    *,
    deps: ChatStreamConsumeDeps,
    state: ChatStreamRuntimeState,
    json_stream: AsyncIterable[dict[str, Any]],
    chat_id: str,
    created_time: int,
    model_name: str,
    request_id: str,
) -> AsyncIterable[str]:
    async for json_obj in json_stream:
        state.response_count += 1
        state.json_objects.append(json_obj)

        deps.logger.debug(
            f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] "
            f"收到响应#{state.response_count}: {json.dumps(json_obj, ensure_ascii=False)[:1000]}"
        )

        if "error" in json_obj:
            error_info = json_obj.get("error", {})
            error_code = error_info.get("code", 0)
            error_message = error_info.get("message", "")
            deps.logger.warning(
                f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] "
                f"上游返回错误: {json.dumps(error_info, ensure_ascii=False)}"
            )

            if error_code == 429 or "RESOURCE_EXHAUSTED" in error_info.get("status", ""):
                quota_type = deps.get_request_quota_type(model_name)
                deps.account_manager.handle_http_error(429, error_message[:200], request_id, quota_type)
                raise HTTPException(status_code=429, detail=f"Upstream quota exhausted: {error_message[:200]}")

        stream_response = json_obj.get("streamAssistResponse", {})
        answer = stream_response.get("answer", {})

        answer_state = answer.get("state", "")
        if answer_state == "SKIPPED":
            skip_reasons = answer.get("assistSkippedReasons", [])
            policy_result = answer.get("customerPolicyEnforcementResult", {})

            if "CUSTOMER_POLICY_VIOLATION" in skip_reasons:
                policy_results = policy_result.get("policyResults", [])
                violation_detail = ""

                for policy in policy_results:
                    armor_result = policy.get("modelArmorEnforcementResult", {})
                    if armor_result:
                        violation_detail = armor_result.get("modelArmorViolation", "")
                        if violation_detail:
                            break

                deps.logger.warning(
                    f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] "
                    f"内容被安全策略阻止: {violation_detail or 'CUSTOMER_POLICY_VIOLATION'}"
                )

                error_text = "\n⚠️ 违反政策\n\n由于提示违反了 Google 定义的安全政策，因此 Gemini 无法回复。\n\n请修改提示以符合安全政策。\n"
                _mark_stream_first_response(request=deps.request, state=state)
                state.full_content += error_text
                chunk = deps.create_chunk(chat_id, created_time, model_name, {"content": error_text}, None)
                yield f"data: {chunk}\n\n"
                continue

            if skip_reasons:
                reason_text = ", ".join(skip_reasons)
                deps.logger.warning(
                    f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] 响应被跳过: {reason_text}"
                )

                error_text = f"\n⚠️ 抱歉，无法生成响应。\n\n原因：{reason_text}\n\n请稍后重试或联系管理员。\n"
                _mark_stream_first_response(request=deps.request, state=state)
                state.full_content += error_text
                chunk = deps.create_chunk(chat_id, created_time, model_name, {"content": error_text}, None)
                yield f"data: {chunk}\n\n"
                continue

        replies = answer.get("replies", [])

        if not replies:
            deps.logger.debug(
                f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] "
                f"响应#{state.response_count}无replies，完整answer结构: {json.dumps(answer, ensure_ascii=False)[:500]}"
            )
        else:
            deps.logger.debug(
                f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] "
                f"响应#{state.response_count}包含{len(replies)}个replies"
            )

        for idx, reply in enumerate(replies):
            content_obj = reply.get("groundedContent", {}).get("content", {})
            text = content_obj.get("text", "")

            if not text:
                deps.logger.debug(
                    f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] "
                    f"Reply#{idx}无text，content_obj结构: {json.dumps(content_obj, ensure_ascii=False)[:300]}"
                )
                continue

            _mark_stream_first_response(request=deps.request, state=state)
            if not state.usage_counted:
                state.usage_counted = True
                deps.account_manager.conversation_count += 1
                deps.account_manager.increment_daily_usage(deps.get_request_quota_type(model_name))

            if content_obj.get("thought"):
                chunk = deps.create_chunk(
                    chat_id,
                    created_time,
                    model_name,
                    {"reasoning_content": text},
                    None,
                )
                yield f"data: {chunk}\n\n"
                continue

            state.full_content += text
            chunk = deps.create_chunk(chat_id, created_time, model_name, {"content": text}, None)
            yield f"data: {chunk}\n\n"

    if state.json_objects:
        file_ids, session_name = deps.parse_generated_media_files(state.json_objects, deps.logger)
        if file_ids and session_name:
            state.file_ids_info = (file_ids, session_name)
            deps.logger.info(
                f"[IMAGE] [{deps.account_manager.config.account_id}] [req_{request_id}] 检测到{len(file_ids)}张生成图片"
            )

    deps.logger.info(
        f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] "
        f"流处理完成: 收到{state.response_count}个响应对象, 累计内容长度{len(state.full_content)}字符"
    )
    if state.response_count > 0 and len(state.full_content) == 0:
        quota_type = deps.get_request_quota_type(model_name)
        if quota_type in ("images", "videos"):
            deps.logger.info(
                f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] 媒体生成请求，无文本内容属正常情况"
            )
            if not state.usage_counted:
                state.usage_counted = True
                deps.account_manager.conversation_count += 1
                deps.account_manager.increment_daily_usage(quota_type)
            return

        deps.logger.warning(
            f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] "
            f"⚠️ 空响应警告: 收到{state.response_count}个响应但无文本内容，可能是思考模型未生成最终回答或上游错误"
        )
        if state.json_objects:
            deps.logger.warning(
                f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] "
                f"第一个响应完整结构: {json.dumps(state.json_objects[0], ensure_ascii=False)}"
            )

        if deps.request is not None:
            deps.request.state.first_response_time = None
        raise HTTPException(status_code=502, detail="Thinking model produced thoughts but no final content")


def build_chat_stream_error_payload(message: str) -> str:
    return f"data: {json.dumps({'error': {'message': message}})}\n\n"


def finalize_chat_stream_response(
    *,
    deps: ChatStreamFinalizeDeps,
    state: ChatStreamRuntimeState,
    start_time: float,
    chat_id: str,
    created_time: int,
    model_name: str,
    request_id: str,
    is_stream: bool,
) -> list[str]:
    if state.full_content:
        response_preview = (
            state.full_content[:500] + "...(已截断)"
            if len(state.full_content) > 500
            else state.full_content
        )
        deps.logger.info(
            f"[CHAT] [{deps.account_manager.config.account_id}] [req_{request_id}] AI响应: {response_preview}"
        )
    else:
        quota_type = deps.get_request_quota_type(model_name)
        if quota_type in ("images", "videos"):
            deps.logger.info(
                f"[CHAT] [{deps.account_manager.config.account_id}] [req_{request_id}] "
                "媒体生成请求，文本响应为空属正常情况"
            )
        else:
            deps.logger.warning(
                f"[CHAT] [{deps.account_manager.config.account_id}] [req_{request_id}] "
                "⚠️ 最终响应为空，请检查上游日志"
            )

    if state.first_response_time:
        latency_ms = int((state.first_response_time - start_time) * 1000)
        deps.uptime_tracker.record_request(model_name, True, latency_ms)
    else:
        deps.uptime_tracker.record_request(model_name, True)

    total_time = time.time() - start_time
    deps.logger.info(
        f"[API] [{deps.account_manager.config.account_id}] [req_{request_id}] 响应完成: {total_time:.2f}秒"
    )

    if not is_stream:
        return []

    final_chunk = deps.create_chunk(chat_id, created_time, model_name, {}, "stop")
    return [f"data: {final_chunk}\n\n", "data: [DONE]\n\n"]


def handle_chat_retry_exception(
    *,
    deps: ChatRetryErrorDeps,
    account_manager: Any,
    error: Exception,
    max_retries: int,
    model: str,
    request_id: str,
    retry_idx: int,
) -> ChatRetryErrorOutcome:
    is_http_exception = isinstance(error, HTTPException)
    status_code = error.status_code if is_http_exception else None
    error_detail = (
        f"HTTP {error.status_code}: {error.detail}"
        if is_http_exception
        else f"{type(error).__name__}: {str(error)[:200]}"
    )

    deps.uptime_tracker.record_request("account_pool", False, status_code=status_code)

    quota_type = deps.get_request_quota_type(model)
    if is_http_exception:
        if status_code == 502:
            deps.logger.warning(
                f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 上游 502 错误，切换账户重试（不触发冷却）"
            )
        else:
            deps.logger.debug(
                f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] HTTP错误，准备按配额类型处理: {quota_type}"
            )
            account_manager.handle_http_error(
                status_code,
                str(error.detail) if hasattr(error, "detail") else "",
                request_id,
                quota_type,
            )
    else:
        account_manager.handle_non_http_error("聊天请求", request_id, quota_type)

    if retry_idx < max_retries - 1:
        deps.logger.warning(
            f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] 切换账户重试 ({retry_idx + 1}/{max_retries})"
        )
        return ChatRetryErrorOutcome(
            error_detail=error_detail,
            should_retry=True,
            status=deps.classify_error_status(status_code, error),
            status_code=status_code,
        )

    deps.logger.error(f"[CHAT] [req_{request_id}] 已达到最大重试次数 ({max_retries})，请求失败")
    status = deps.classify_error_status(status_code, error)
    return ChatRetryErrorOutcome(
        error_detail=error_detail,
        should_retry=False,
        status=status,
        status_code=status_code,
        stream_error_message=f"Max retries ({max_retries}) exceeded: {error_detail}",
    )


async def handle_chat_failover_error(
    *,
    deps: ChatRetryFailoverErrorDeps,
    error: Exception,
    request_id: str,
) -> ChatRetryErrorOutcome:
    error_type = type(error).__name__
    deps.logger.error(f"[CHAT] [req_{request_id}] 账户切换失败 ({error_type}): {str(error)}")
    status_code = error.status_code if isinstance(error, HTTPException) else None
    deps.uptime_tracker.record_request("account_pool", False, status_code=status_code)

    status = deps.classify_error_status(status_code, error)
    error_detail = f"Account Failover Failed: {str(error)[:200]}"
    await deps.finalize_result(status, status_code, error_detail)
    return ChatRetryErrorOutcome(
        error_detail=error_detail,
        should_retry=False,
        status=status,
        status_code=status_code,
        stream_error_message="Account Failover Failed",
    )


async def stream_chat_response_with_retry(
    *,
    deps: ChatResponseRetryDeps,
    context: ChatResponseRetryContext,
    account_manager: Any,
) -> AsyncIterable[str]:
    available_accounts = deps.multi_account_mgr.get_available_accounts(context.required_quota_types)
    max_retries = min(deps.max_account_switch_tries, len(available_accounts))

    current_retry_mode = context.initial_retry_mode
    current_file_ids: list[str] = []

    for retry_idx in range(max_retries):
        try:
            retry_preparation = await prepare_chat_retry_attempt(
                deps=deps.prepare_retry_deps,
                account_manager=account_manager,
                base_text=context.initial_text,
                conversation_key=context.conversation_key,
                current_file_ids=current_file_ids,
                current_images=context.current_images,
                current_retry_mode=current_retry_mode,
                messages=context.messages,
                request_id=context.request_id,
            )
            current_session = retry_preparation.session_id
            current_text = retry_preparation.text_content
            current_retry_mode = retry_preparation.retry_mode
            current_file_ids = retry_preparation.file_ids

            async for chunk in deps.stream_chat(
                current_session,
                current_text,
                current_file_ids,
                context.model,
                context.chat_id,
                context.created_time,
                account_manager,
                context.stream,
                context.request_id,
                context.request,
            ):
                yield chunk

            if getattr(context.request.state, "first_response_time", None) is None:
                raise HTTPException(status_code=502, detail="Empty response from upstream")

            deps.uptime_tracker.record_request("account_pool", True)
            await deps.finalize_result("success", 200, None)
            break
        except (httpx.HTTPError, ssl.SSLError, HTTPException) as exc:
            retry_error = handle_chat_retry_exception(
                deps=deps.retry_error_deps,
                account_manager=account_manager,
                error=exc,
                max_retries=max_retries,
                model=context.model,
                request_id=context.request_id,
                retry_idx=retry_idx,
            )
            if retry_error.should_retry:
                try:
                    failover_result = await failover_chat_retry_account(
                        deps=deps.retry_failover_deps,
                        account_manager=account_manager,
                        conversation_key=context.conversation_key,
                        request_id=context.request_id,
                        required_quota_types=context.required_quota_types,
                    )
                    account_manager = failover_result.account_manager
                    current_retry_mode = failover_result.retry_mode
                    current_file_ids = failover_result.file_ids
                except Exception as create_err:
                    failover_error = await handle_chat_failover_error(
                        deps=deps.retry_failover_error_deps,
                        error=create_err,
                        request_id=context.request_id,
                    )
                    if context.stream and failover_error.stream_error_message:
                        yield build_chat_stream_error_payload(failover_error.stream_error_message)
                    return
            else:
                await deps.finalize_result(
                    retry_error.status,
                    retry_error.status_code,
                    retry_error.error_detail,
                )
                if context.stream and retry_error.stream_error_message:
                    yield build_chat_stream_error_payload(retry_error.stream_error_message)
                return


async def collect_non_stream_chat_response(
    *,
    chunk_stream: AsyncIterable[str],
    logger: Any,
    account_id: str,
    request_id: str,
    chat_id: str,
    created_time: int,
    model: str,
) -> dict[str, Any]:
    full_content = ""
    full_reasoning = ""

    async for chunk_str in chunk_stream:
        if chunk_str.startswith("data: [DONE]"):
            break
        if not chunk_str.startswith("data: "):
            continue

        try:
            data = json.loads(chunk_str[6:])
            delta = data["choices"][0]["delta"]
            if "content" in delta:
                full_content += delta["content"]
            if "reasoning_content" in delta:
                full_reasoning += delta["reasoning_content"]
        except json.JSONDecodeError as exc:
            logger.error(f"[CHAT] [{account_id}] [req_{request_id}] JSON解析失败: {str(exc)}")
        except (KeyError, IndexError) as exc:
            logger.error(f"[CHAT] [{account_id}] [req_{request_id}] 响应格式错误 ({type(exc).__name__}): {str(exc)}")

    message = {"role": "assistant", "content": full_content}
    if full_reasoning:
        message["reasoning_content"] = full_reasoning

    logger.info(f"[CHAT] [{account_id}] [req_{request_id}] 非流式响应完成")
    response_preview = full_content[:500] + "...(已截断)" if len(full_content) > 500 else full_content
    logger.info(f"[CHAT] [{account_id}] [req_{request_id}] AI响应: {response_preview}")

    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created_time,
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def handle_chat_request(
    *,
    deps: ChatRequestHandlerDeps,
    req: Any,
    request: Any,
) -> Any:
    request_id = str(uuid.uuid4())[:6]
    start_ts = time.time()
    request.state.first_response_time = None
    message_count = len(req.messages)

    monitor_recorded = False
    account_manager = None

    chat_metrics_deps = ChatMetricsDeps(
        build_recent_conversation_entry=deps.build_recent_conversation_entry,
        global_stats=deps.global_stats,
        multi_account_mgr=deps.multi_account_mgr,
        save_stats=deps.save_stats,
        stats_db=deps.stats_db,
        stats_lock=deps.stats_lock,
        uptime_tracker=deps.uptime_tracker,
    )

    async def finalize_result(
        status: str,
        status_code: int | None = None,
        error_detail: str | None = None,
    ) -> None:
        nonlocal monitor_recorded
        if monitor_recorded:
            return
        monitor_recorded = True
        await finalize_chat_request_result(
            deps=chat_metrics_deps,
            request=request,
            request_id=request_id,
            model=req.model if req else None,
            message_count=message_count,
            start_ts=start_ts,
            status=status,
            status_code=status_code,
            error_detail=error_detail,
            account_manager=account_manager,
        )

    await record_chat_request_start(deps=chat_metrics_deps, model=req.model)

    request_prelude = build_chat_request_prelude(
        request=request,
        req=req,
        get_required_quota_types=deps.get_required_quota_types,
        get_conversation_key=deps.get_conversation_key,
    )

    model_not_found_error = build_model_not_found_error(
        model=req.model,
        model_mapping=deps.model_mapping,
        virtual_models=deps.virtual_models,
    )
    if model_not_found_error:
        deps.logger.error(f"[CHAT] [req_{request_id}] 模型不存在: {req.model}")
        await finalize_result("error", 404, f"HTTP 404: Model '{req.model}' not found")
        raise model_not_found_error

    request.state.model = req.model

    session_resolution = await resolve_chat_session(
        deps=ChatSessionResolveDeps(
            classify_error_status=classify_chat_error_status,
            create_google_session=deps.create_google_session,
            finalize_result=finalize_result,
            http_client=deps.http_client,
            logger=deps.logger,
            max_account_switch_tries=deps.max_account_switch_tries,
            multi_account_mgr=deps.multi_account_mgr,
            request=request,
            uptime_tracker=deps.uptime_tracker,
            user_agent=deps.user_agent,
        ),
        request_id=request_id,
        required_quota_types=request_prelude.required_quota_types,
        conversation_key=request_prelude.conversation_key,
    )
    account_manager = session_resolution.account_manager

    chat_execution = await prepare_chat_response_execution(
        deps=ChatResponseExecutionSetupDeps(
            build_full_context_text=deps.build_full_context_text,
            classify_error_status=classify_chat_error_status,
            create_google_session=deps.create_google_session,
            finalize_result=finalize_result,
            get_request_quota_type=deps.get_request_quota_type,
            http_client=deps.http_client,
            logger=deps.logger,
            max_account_switch_tries=deps.max_account_switch_tries,
            multi_account_mgr=deps.multi_account_mgr,
            parse_last_message=deps.parse_last_message,
            request=request,
            stream_chat=deps.stream_chat,
            upload_context_file=deps.upload_context_file,
            uptime_tracker=deps.uptime_tracker,
            user_agent=deps.user_agent,
        ),
        account_manager=account_manager,
        conversation_key=request_prelude.conversation_key,
        is_new_conversation=session_resolution.is_new_conversation,
        messages=req.messages,
        model=req.model,
        request_id=request_id,
        required_quota_types=request_prelude.required_quota_types,
        stream=req.stream,
    )

    response_stream = stream_chat_response_with_retry(
        deps=chat_execution.retry_deps,
        context=chat_execution.retry_context,
        account_manager=account_manager,
    )

    if req.stream:
        return StreamingResponse(response_stream, media_type="text/event-stream")

    return await collect_non_stream_chat_response(
        chunk_stream=response_stream,
        logger=deps.logger,
        account_id=account_manager.config.account_id,
        request_id=request_id,
        chat_id=chat_execution.chat_id,
        created_time=chat_execution.created_time,
        model=req.model,
    )


async def record_chat_request_start(*, deps: ChatMetricsDeps, model: str) -> None:
    async with deps.stats_lock:
        timestamp = time.time()
        deps.global_stats["total_requests"] += 1
        deps.global_stats["request_timestamps"].append(timestamp)
        deps.global_stats.setdefault("model_request_timestamps", {})
        deps.global_stats["model_request_timestamps"].setdefault(model, []).append(timestamp)
        await deps.save_stats(deps.global_stats)


async def finalize_chat_request_result(
    *,
    deps: ChatMetricsDeps,
    request: Any,
    request_id: str,
    model: str | None,
    message_count: int,
    start_ts: float,
    status: str,
    status_code: int | None = None,
    error_detail: str | None = None,
    account_manager: Any = None,
) -> None:
    duration_s = time.time() - start_ts
    first_response_time = getattr(request.state, "first_response_time", None)
    if first_response_time:
        latency_ms = int((first_response_time - start_ts) * 1000)
    else:
        latency_ms = int(duration_s * 1000)

    deps.uptime_tracker.record_request("api_service", status == "success", latency_ms, status_code)

    entry = deps.build_recent_conversation_entry(
        request_id=request_id,
        model=model,
        message_count=message_count,
        start_ts=start_ts,
        status=status,
        duration_s=duration_s if status == "success" else None,
        error_detail=error_detail,
    )

    async with deps.stats_lock:
        deps.global_stats.setdefault("failure_timestamps", [])
        deps.global_stats.setdefault("rate_limit_timestamps", [])
        deps.global_stats.setdefault("recent_conversations", [])
        deps.global_stats.setdefault("success_count", 0)
        deps.global_stats.setdefault("failed_count", 0)
        deps.global_stats.setdefault("account_conversations", {})
        deps.global_stats.setdefault("account_failures", {})
        deps.global_stats.setdefault("response_times", deque(maxlen=10000))

        if status == "success":
            ttfb_ms = int((first_response_time - start_ts) * 1000) if first_response_time else latency_ms
            total_ms = int((time.time() - start_ts) * 1000)
            model_name = model or "unknown"

            deps.global_stats["response_times"].append(
                {
                    "timestamp": time.time(),
                    "ttfb_ms": ttfb_ms,
                    "total_ms": total_ms,
                    "model": model_name,
                }
            )

            asyncio.create_task(
                deps.stats_db.insert_request_log(
                    timestamp=time.time(),
                    model=model_name,
                    ttfb_ms=ttfb_ms,
                    total_ms=total_ms,
                    status=status,
                    status_code=status_code,
                )
            )
        else:
            model_name = model or "unknown"
            asyncio.create_task(
                deps.stats_db.insert_request_log(
                    timestamp=time.time(),
                    model=model_name,
                    ttfb_ms=None,
                    total_ms=None,
                    status=status,
                    status_code=status_code,
                )
            )

        if status != "success":
            deps.global_stats["failed_count"] += 1
            deps.global_stats["failure_timestamps"].append(time.time())
            if status_code == 429:
                deps.global_stats["rate_limit_timestamps"].append(time.time())

            failure_account_id = None
            if account_manager:
                account_manager.failure_count += 1
                failure_account_id = account_manager.config.account_id
                deps.global_stats["account_failures"][failure_account_id] = account_manager.failure_count
            else:
                failure_account_id = getattr(request.state, "last_account_id", None)
                if failure_account_id and failure_account_id in deps.multi_account_mgr.accounts:
                    account_mgr = deps.multi_account_mgr.accounts[failure_account_id]
                    account_mgr.failure_count += 1
                    deps.global_stats["account_failures"][failure_account_id] = account_mgr.failure_count
                elif failure_account_id:
                    deps.global_stats["account_failures"][failure_account_id] = (
                        deps.global_stats["account_failures"].get(failure_account_id, 0) + 1
                    )
        else:
            deps.global_stats["success_count"] += 1
            if account_manager:
                deps.global_stats["account_conversations"][account_manager.config.account_id] = (
                    account_manager.conversation_count
                )

        deps.global_stats["recent_conversations"].append(entry)
        deps.global_stats["recent_conversations"] = deps.global_stats["recent_conversations"][-60:]
        await deps.save_stats(deps.global_stats)
