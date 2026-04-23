from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from fastapi import FastAPI, Header, Request

from app.api.schemas import ChatRequest


@dataclass(frozen=True)
class ChatRouteDeps:
    api_key: Callable[[], str]
    chat_handler: Callable[[ChatRequest, Request, Optional[str]], Awaitable[dict[str, Any]]]
    get_model_ids: Callable[[], list[str]]
    verify_api_key: Callable[[str, Optional[str]], Any]


def register_chat_routes(app: FastAPI, deps: ChatRouteDeps) -> None:
    @app.get("/v1/models")
    async def list_models(authorization: str = Header(None)):
        del authorization

        now = int(time.time())
        data = [
            {
                "id": model_id,
                "object": "model",
                "created": now,
                "owned_by": "google",
                "permission": [],
            }
            for model_id in deps.get_model_ids()
        ]
        return {"object": "list", "data": data}

    @app.get("/v1/models/{model_id}")
    async def get_model(model_id: str, authorization: str = Header(None)):
        del authorization
        return {"id": model_id, "object": "model"}

    @app.post("/v1/chat/completions")
    async def chat(
        req: ChatRequest,
        request: Request,
        authorization: Optional[str] = Header(None),
    ):
        deps.verify_api_key(deps.api_key(), authorization)
        return await deps.chat_handler(req, request, authorization)
