from __future__ import annotations

import base64
import logging
import re
import uuid
from typing import Any, Callable


_B64_IMAGE_PATTERN = re.compile(r"!\[.*?\]\(data:([^;]+);base64,([^\)]+)\)")
_URL_IMAGE_PATTERN = re.compile(r"!\[.*?\]\((https?://[^\)]+)\)")


def extract_markdown_image_payloads(message_content: str) -> tuple[list[tuple[str, str]], list[str]]:
    return _B64_IMAGE_PATTERN.findall(message_content), _URL_IMAGE_PATTERN.findall(message_content)


def resolve_image_response_format(image_output_format: str) -> str:
    return "b64_json" if image_output_format == "base64" else "url"


async def build_openai_image_data(
    *,
    message_content: str,
    desired_count: int,
    revised_prompt: str,
    response_format: str,
    request: Any,
    http_client: Any,
    get_base_url: Callable[[Any], str],
    image_dir: str,
    save_image_file: Callable[[bytes, str, str, str, str, str], str],
    logger: logging.Logger,
    request_id: str,
    log_prefix: str,
    chat_id_prefix: str,
    file_id_prefix: str,
) -> list[dict[str, str]]:
    b64_matches, url_matches = extract_markdown_image_payloads(message_content)
    data_list: list[dict[str, str]] = []

    if response_format == "b64_json":
        for mime, b64_data in b64_matches[:desired_count]:
            data_list.append({"b64_json": b64_data, "revised_prompt": revised_prompt})

        if not data_list and url_matches:
            for url in url_matches[:desired_count]:
                try:
                    response = await http_client.get(url)
                    if response.status_code == 200:
                        b64_data = base64.b64encode(response.content).decode()
                        data_list.append({"b64_json": b64_data, "revised_prompt": revised_prompt})
                    else:
                        logger.error(
                            "[%s] [req_%s] Failed to download image: %s, status=%s",
                            log_prefix,
                            request_id,
                            url,
                            response.status_code,
                        )
                except Exception as exc:
                    logger.error(
                        "[%s] [req_%s] Failed to download image: %s, %s",
                        log_prefix,
                        request_id,
                        url,
                        exc,
                    )
        return data_list

    for url in url_matches[:desired_count]:
        data_list.append({"url": url, "revised_prompt": revised_prompt})

    if data_list or not b64_matches:
        return data_list

    base_url = get_base_url(request)
    chat_id = f"{chat_id_prefix}-{uuid.uuid4()}"
    for mime, b64_data in b64_matches[:desired_count]:
        try:
            image_bytes = base64.b64decode(b64_data)
            file_id = f"{file_id_prefix}-{uuid.uuid4()}"
            url = save_image_file(image_bytes, chat_id, file_id, mime, base_url, image_dir)
            data_list.append({"url": url, "revised_prompt": revised_prompt})
        except Exception as exc:
            logger.error(
                "[%s] [req_%s] Failed to persist image asset: %s",
                log_prefix,
                request_id,
                exc,
            )

    return data_list
