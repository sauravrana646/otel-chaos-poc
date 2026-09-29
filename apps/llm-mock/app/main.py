"""Deterministic OpenAI-compatible LLM mock for load and fault scenarios."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import defaultdict
from typing import Any, AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

APP = FastAPI(title="llm-mock", version="0.1.0")

_lock = threading.Lock()
_fail_then_success: dict[str, int] = defaultdict(int)
_state = {
    "delay_ms": 50,
    "mode": "normal",  # normal | fail-then-success | persistent-429 | persistent-503
}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    max_tokens: int | None = 128
    stream: bool = False


@APP.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@APP.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ready"}


@APP.post("/admin/reset")
def admin_reset() -> dict[str, str]:
    with _lock:
        _fail_then_success.clear()
        _state["delay_ms"] = 50
        _state["mode"] = "normal"
    return {"status": "reset"}


@APP.post("/admin/config")
def admin_config(body: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        if "delay_ms" in body:
            _state["delay_ms"] = int(body["delay_ms"])
        if "mode" in body:
            mode = str(body["mode"])
            if mode not in {"normal", "fail-then-success", "persistent-429", "persistent-503"}:
                raise HTTPException(status_code=400, detail="invalid mode")
            _state["mode"] = mode
        return dict(_state)


@APP.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    x_poc_scenario: str | None = Header(default=None, alias="X-POC-Scenario"),
) -> Any:
    request_id = x_request_id or request.headers.get("x-request-id") or "anonymous"
    scenario = x_poc_scenario or "normal"

    with _lock:
        delay_ms = int(_state["delay_ms"])
        mode = _state["mode"]
        if scenario == "retry-success":
            mode = "fail-then-success"
        elif scenario == "retry-exhaust":
            mode = "persistent-503"

    await asyncio.sleep(delay_ms / 1000.0)

    if mode == "persistent-429":
        raise HTTPException(status_code=429, detail="rate limited")
    if mode == "persistent-503":
        raise HTTPException(status_code=503, detail="unavailable")

    if mode == "fail-then-success":
        with _lock:
            count = _fail_then_success[request_id]
            if count < 2:
                _fail_then_success[request_id] = count + 1
                raise HTTPException(status_code=503, detail="transient unavailable")
            # third attempt succeeds; leave counter so repeats stay successful

    content = f"mock-recommendation for {request_id} scenario={scenario}"
    created = int(time.time())

    if body.stream or scenario == "stream":
        return StreamingResponse(
            _stream(content, body.model, created),
            media_type="text/event-stream",
        )

    return {
        "id": f"chatcmpl-{request_id}",
        "object": "chat.completion",
        "created": created,
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 32, "completion_tokens": 16, "total_tokens": 48},
    }


async def _stream(content: str, model: str, created: int) -> AsyncIterator[str]:
    chunk_id = f"chatcmpl-stream-{created}"
    for token in content.split(" "):
        payload = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": token + " "}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(payload)}\n\n"
        await asyncio.sleep(0.01)
    done = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done)}\n\n"
    yield "data: [DONE]\n\n"
