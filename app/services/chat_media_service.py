from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


def parse_generated_media_files(
    data_list: list[dict[str, Any]],
    logger: Any,
) -> tuple[list[dict[str, str]], str]:
    file_refs: list[dict[str, str]] = []
    session_name = ""
    seen_file_ids: set[str] = set()

    for data in data_list:
        stream_response = data.get("streamAssistResponse")
        if not stream_response:
            continue

        session_info = stream_response.get("sessionInfo", {})
        if session_info.get("session"):
            session_name = str(session_info["session"])

        answer = stream_response.get("answer") or {}
        replies = answer.get("replies") or []

        for reply in replies:
            content = reply.get("groundedContent", {}).get("content", {})
            file_info = content.get("file")
            if not file_info or not file_info.get("fileId"):
                continue

            file_id = str(file_info["fileId"])
            if file_id in seen_file_ids:
                continue

            seen_file_ids.add(file_id)
            mime_type = str(file_info.get("mimeType", "image/png"))
            logger.debug(f"[PARSE] 解析媒体文件: fileId={file_id}, mimeType={mime_type}")
            file_refs.append({"fileId": file_id, "mimeType": mime_type})

    return file_refs, session_name


def process_generated_media(
    *,
    data: bytes,
    mime: str,
    chat_id: str,
    file_id: str,
    base_url: str,
    idx: int,
    request_id: str,
    account_id: str,
    image_dir: str,
    image_output_format: str,
    logger: Any,
    save_media_file: Callable[..., str],
    video_dir: str,
    video_output_format: str,
) -> str:
    logger.info(f"[MEDIA] [{account_id}] [req_{request_id}] 处理媒体{idx}: MIME={mime}")

    if mime.startswith("video/"):
        url = save_media_file(data, chat_id, file_id, mime, base_url, video_dir, "videos")
        logger.info(f"[VIDEO] [{account_id}] [req_{request_id}] 视频{idx}已保存: {url}")

        if video_output_format == "html":
            return (
                '\n\n<video controls width="100%" style="max-width: 640px;">'
                f'<source src="{url}" type="{mime}">'
                "您的浏览器不支持视频播放</video>\n\n"
            )
        if video_output_format == "markdown":
            return f"\n\n![生成的视频]({url})\n\n"
        return f"\n\n{url}\n\n"

    if image_output_format == "base64":
        encoded = base64.b64encode(data).decode()
        logger.info(f"[IMAGE] [{account_id}] [req_{request_id}] 图片{idx}已编码为base64")
        return f"\n\n![生成的图片](data:{mime};base64,{encoded})\n\n"

    url = save_media_file(data, chat_id, file_id, mime, base_url, image_dir)
    logger.info(f"[IMAGE] [{account_id}] [req_{request_id}] 图片{idx}已保存: {url}")
    return f"\n\n![生成的图片]({url})\n\n"


def _mark_first_response(request: Any, first_response_time: float | None) -> float:
    if first_response_time is None:
        first_response_time = time.time()
        if request is not None:
            request.state.first_response_time = first_response_time
    return first_response_time


@dataclass(frozen=True)
class ChatMediaFollowupDeps:
    account_manager: Any
    create_chunk: Callable[[str, int, str, dict[str, Any], str | None], str]
    download_media_file: Callable[..., Awaitable[bytes]]
    get_base_url: Callable[[Any], str]
    get_file_metadata: Callable[..., Awaitable[dict[str, Any]]]
    http_client: Any
    image_dir: str
    image_output_format: str
    logger: Any
    request: Any
    save_media_file: Callable[..., str]
    user_agent: str
    video_dir: str
    video_output_format: str


@dataclass(frozen=True)
class ChatMediaFollowupResult:
    chunks: list[str]
    first_response_time: float | None


async def collect_generated_media_followups(
    *,
    account_manager: Any,
    base_url: str,
    chat_id: str,
    create_chunk: Callable[[str, int, str, dict[str, Any], str | None], str],
    created_time: int,
    download_media_file: Callable[..., Awaitable[bytes]],
    file_refs: list[dict[str, str]],
    get_file_metadata: Callable[..., Awaitable[dict[str, Any]]],
    http_client: Any,
    image_dir: str,
    image_output_format: str,
    logger: Any,
    model_name: str,
    request: Any,
    request_id: str,
    save_media_file: Callable[..., str],
    session_name: str,
    user_agent: str,
    video_dir: str,
    video_output_format: str,
) -> tuple[list[str], float | None]:
    first_response_time: float | None = None

    try:
        file_metadata = await get_file_metadata(
            account_manager,
            session_name,
            http_client,
            user_agent,
            request_id,
        )

        download_tasks: list[tuple[str, str, Awaitable[bytes]]] = []
        for file_ref in file_refs:
            file_id = file_ref["fileId"]
            mime = file_ref["mimeType"]
            meta = file_metadata.get(file_id, {})
            resolved_mime = str(meta.get("mimeType", mime))
            resolved_session = str(meta.get("session") or session_name)
            task = download_media_file(
                account_manager,
                resolved_session,
                file_id,
                http_client,
                user_agent,
                request_id,
            )
            download_tasks.append((file_id, resolved_mime, task))

        results = await asyncio.gather(
            *[task for _, _, task in download_tasks],
            return_exceptions=True,
        )

        chunks: list[str] = []
        success_count = 0

        for idx, ((file_id, mime, _), result) in enumerate(zip(download_tasks, results), 1):
            if isinstance(result, Exception):
                logger.error(
                    f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] "
                    f"媒体{idx}下载失败: {type(result).__name__}: {str(result)[:100]}"
                )
                first_response_time = _mark_first_response(request, first_response_time)
                error_msg = f"\n\n⚠️ 图片 {idx} 下载失败\n\n"
                chunks.append(
                    f"data: {create_chunk(chat_id, created_time, model_name, {'content': error_msg}, None)}\n\n"
                )
                continue

            try:
                markdown = process_generated_media(
                    data=result,
                    mime=mime,
                    chat_id=chat_id,
                    file_id=file_id,
                    base_url=base_url,
                    idx=idx,
                    request_id=request_id,
                    account_id=account_manager.config.account_id,
                    image_dir=image_dir,
                    image_output_format=image_output_format,
                    logger=logger,
                    save_media_file=save_media_file,
                    video_dir=video_dir,
                    video_output_format=video_output_format,
                )
                success_count += 1
                first_response_time = _mark_first_response(request, first_response_time)
                chunks.append(
                    f"data: {create_chunk(chat_id, created_time, model_name, {'content': markdown}, None)}\n\n"
                )
            except Exception as exc:
                logger.error(
                    f"[MEDIA] [{account_manager.config.account_id}] [req_{request_id}] "
                    f"媒体{idx}处理失败: {str(exc)[:100]}"
                )
                first_response_time = _mark_first_response(request, first_response_time)
                error_msg = f"\n\n⚠️ 媒体 {idx} 处理失败\n\n"
                chunks.append(
                    f"data: {create_chunk(chat_id, created_time, model_name, {'content': error_msg}, None)}\n\n"
                )

        logger.info(
            f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] "
            f"媒体后处理完成: {success_count}/{len(file_refs)} 成功"
        )
        return chunks, first_response_time
    except Exception as exc:
        logger.error(
            f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] "
            f"媒体后处理失败: {type(exc).__name__}: {str(exc)[:100]}"
        )
        first_response_time = _mark_first_response(request, first_response_time)
        error_msg = f"\n\n⚠️ 媒体后处理失败: {type(exc).__name__}\n\n"
        return [
            f"data: {create_chunk(chat_id, created_time, model_name, {'content': error_msg}, None)}\n\n"
        ], first_response_time


async def execute_generated_media_followups(
    *,
    deps: ChatMediaFollowupDeps,
    file_ids_info: tuple[list[dict[str, str]], str],
    chat_id: str,
    created_time: int,
    model_name: str,
    request_id: str,
) -> ChatMediaFollowupResult:
    file_refs, session_name = file_ids_info

    try:
        base_url = deps.get_base_url(deps.request) if deps.request else ""
        chunks, first_response_time = await collect_generated_media_followups(
            account_manager=deps.account_manager,
            base_url=base_url,
            chat_id=chat_id,
            create_chunk=deps.create_chunk,
            created_time=created_time,
            download_media_file=deps.download_media_file,
            file_refs=file_refs,
            get_file_metadata=deps.get_file_metadata,
            http_client=deps.http_client,
            image_dir=deps.image_dir,
            image_output_format=deps.image_output_format,
            logger=deps.logger,
            model_name=model_name,
            request=deps.request,
            request_id=request_id,
            save_media_file=deps.save_media_file,
            session_name=session_name,
            user_agent=deps.user_agent,
            video_dir=deps.video_dir,
            video_output_format=deps.video_output_format,
        )
        return ChatMediaFollowupResult(
            chunks=chunks,
            first_response_time=first_response_time,
        )
    except Exception as exc:
        deps.logger.error(
            f"[IMAGE] [{deps.account_manager.config.account_id}] [req_{request_id}] "
            f"图片处理失败: {type(exc).__name__}: {str(exc)[:100]}"
        )
        first_response_time = _mark_first_response(deps.request, None)
        error_msg = f"\n\n⚠️ 图片处理失败: {type(exc).__name__}\n\n"
        chunk = f"data: {deps.create_chunk(chat_id, created_time, model_name, {'content': error_msg}, None)}\n\n"
        return ChatMediaFollowupResult(
            chunks=[chunk],
            first_response_time=first_response_time,
        )
