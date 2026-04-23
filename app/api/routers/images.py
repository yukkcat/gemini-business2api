from __future__ import annotations

import base64
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from fastapi import FastAPI, File, Form, Header, Request, UploadFile

from app.api.schemas import ChatRequest, ImageGenerationRequest, Message
from app.services import build_openai_image_data, resolve_image_response_format


@dataclass(frozen=True)
class ImageRouteDeps:
    api_key: Callable[[], str]
    chat_handler: Callable[[ChatRequest, Request, Optional[str]], Awaitable[dict[str, Any]]]
    config_manager: Any
    get_base_url: Callable[[Request], str]
    get_http_client: Callable[[], Any]
    image_dir: str
    logger: logging.Logger
    save_image_file: Callable[[bytes, str, str, str, str, str], str]
    verify_api_key: Callable[[str, Optional[str]], Any]


def register_image_routes(app: FastAPI, deps: ImageRouteDeps) -> None:
    @app.post("/v1/images/generations")
    async def generate_images(
        req: ImageGenerationRequest,
        request: Request,
        authorization: Optional[str] = Header(None),
    ):
        deps.verify_api_key(deps.api_key(), authorization)
        request_id = str(uuid.uuid4())[:6]

        chat_req = ChatRequest(
            model=req.model,
            messages=[Message(role="user", content=req.prompt)],
            stream=False,
        )

        deps.logger.info(
            "[IMAGE-GEN] [req_%s] Received image generation request: model=%s, prompt=%s",
            request_id,
            req.model,
            req.prompt[:100],
        )

        try:
            chat_response = await deps.chat_handler(chat_req, request, authorization)
            message_content = chat_response["choices"][0]["message"]["content"]
            system_format = deps.config_manager.image_output_format
            response_format = resolve_image_response_format(system_format)

            deps.logger.info(
                "[IMAGE-GEN] [req_%s] Using configured response format: %s -> %s",
                request_id,
                system_format,
                response_format,
            )

            data_list = await build_openai_image_data(
                message_content=message_content,
                desired_count=req.n,
                revised_prompt=req.prompt,
                response_format=response_format,
                request=request,
                http_client=deps.get_http_client(),
                get_base_url=deps.get_base_url,
                image_dir=deps.image_dir,
                save_image_file=deps.save_image_file,
                logger=deps.logger,
                request_id=request_id,
                log_prefix="IMAGE-GEN",
                chat_id_prefix="img",
                file_id_prefix="gen",
            )

            deps.logger.info(
                "[IMAGE-GEN] [req_%s] Image generation completed: %s items",
                request_id,
                len(data_list),
            )
            return {"created": int(time.time()), "data": data_list}
        except Exception as exc:
            deps.logger.error(
                "[IMAGE-GEN] [req_%s] Image generation failed: %s: %s",
                request_id,
                type(exc).__name__,
                exc,
            )
            raise

    @app.post("/v1/images/edits")
    async def edit_images(
        request: Request,
        image: UploadFile = File(..., description="Original image to edit"),
        prompt: str = Form(..., description="Edit prompt"),
        model: str = Form("gemini-imagen"),
        n: int = Form(1),
        size: str = Form("1024x1024"),
        response_format: Optional[str] = Form(None),
        mask: Optional[UploadFile] = File(None, description="Optional mask image"),
        authorization: Optional[str] = Header(None),
    ):
        del size, response_format

        deps.verify_api_key(deps.api_key(), authorization)
        request_id = str(uuid.uuid4())[:6]

        try:
            image_bytes = await image.read()
            image_b64 = base64.b64encode(image_bytes).decode()
            mime_type = image.content_type or "image/png"
            data_uri = f"data:{mime_type};base64,{image_b64}"

            deps.logger.info(
                "[IMAGE-EDIT] [req_%s] Received image edit request: model=%s, image_size=%s bytes, mime=%s, prompt=%s",
                request_id,
                model,
                len(image_bytes),
                mime_type,
                prompt[:100],
            )

            content_parts: list[dict[str, Any]] = [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": prompt},
            ]

            if mask is not None:
                mask_bytes = await mask.read()
                mask_b64 = base64.b64encode(mask_bytes).decode()
                mask_mime = mask.content_type or "image/png"
                mask_uri = f"data:{mask_mime};base64,{mask_b64}"
                content_parts.insert(1, {"type": "image_url", "image_url": {"url": mask_uri}})
                deps.logger.info(
                    "[IMAGE-EDIT] [req_%s] Included mask image: %s bytes",
                    request_id,
                    len(mask_bytes),
                )

            chat_req = ChatRequest(
                model=model,
                messages=[Message(role="user", content=content_parts)],
                stream=False,
            )

            chat_response = await deps.chat_handler(chat_req, request, authorization)
            message_content = chat_response["choices"][0]["message"]["content"]
            system_format = deps.config_manager.image_output_format
            resolved_format = resolve_image_response_format(system_format)

            deps.logger.info(
                "[IMAGE-EDIT] [req_%s] Using configured response format: %s -> %s",
                request_id,
                system_format,
                resolved_format,
            )

            data_list = await build_openai_image_data(
                message_content=message_content,
                desired_count=n,
                revised_prompt=prompt,
                response_format=resolved_format,
                request=request,
                http_client=deps.get_http_client(),
                get_base_url=deps.get_base_url,
                image_dir=deps.image_dir,
                save_image_file=deps.save_image_file,
                logger=deps.logger,
                request_id=request_id,
                log_prefix="IMAGE-EDIT",
                chat_id_prefix="img-edit",
                file_id_prefix="edit",
            )

            deps.logger.info(
                "[IMAGE-EDIT] [req_%s] Image edit completed: %s items",
                request_id,
                len(data_list),
            )
            return {"created": int(time.time()), "data": data_list}
        except Exception as exc:
            deps.logger.error(
                "[IMAGE-EDIT] [req_%s] Image edit failed: %s: %s",
                request_id,
                type(exc).__name__,
                exc,
            )
            raise
