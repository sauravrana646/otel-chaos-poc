"""LLM service — retries for mock profile only; no OTel init in application code."""

from __future__ import annotations

import os
import random
import time
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException
from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import BaseModel

APP = FastAPI(title="python-llm", version="0.1.0")

DB_DSN = os.getenv(
    "DB_DSN",
    "postgresql://poc_app:poc_app@toxiproxy:5432/poc",
)
PROVIDER_BASE_URL = os.getenv("PROVIDER_BASE_URL", "http://llm-mock:8080/v1")
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "mock-key")
PROVIDER_MODEL = os.getenv("PROVIDER_MODEL", "mock-gpt")
PROFILE = os.getenv("LLM_PROFILE", "mock")  # mock | openrouter
MAX_ATTEMPTS = 1 if PROFILE == "openrouter" else 3
ATTEMPT_TIMEOUT = 30.0 if PROFILE == "openrouter" else 2.0
BACKOFF_MS = (100, 200)


class GenerateRequest(BaseModel):
    request_id: str
    item_id: str
    name: str
    category: str
    context: str
    scenario: str = "normal"


class GenerateResponse(BaseModel):
    result: str
    model: str | None = None
    status: str


@APP.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@APP.get("/readyz")
def readyz() -> dict[str, str]:
    with psycopg.connect(DB_DSN, connect_timeout=2) as conn:
        conn.execute("SELECT 1")
    return {"status": "ready"}


@APP.post("/generate", response_model=GenerateResponse)
def generate(body: GenerateRequest) -> GenerateResponse:
    existing = _read_existing(body.request_id)
    if existing is not None:
        return GenerateResponse(result=existing["result"], model=existing["model"], status="ok")

    client = OpenAI(
        api_key=PROVIDER_API_KEY,
        base_url=PROVIDER_BASE_URL,
        max_retries=0,
        timeout=ATTEMPT_TIMEOUT,
    )

    prompt = (
        f"Recommend next action for item {body.item_id} ({body.name}/{body.category}). "
        f"Context: {body.context}. scenario={body.scenario}"
    )

    last_error: Exception | None = None
    completion_text = ""
    model_name = PROVIDER_MODEL

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            extra_headers = {"X-Request-Id": body.request_id, "X-POC-Scenario": body.scenario}
            resp = client.chat.completions.create(
                model=PROVIDER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=128,
                extra_headers=extra_headers,
            )
            choice = resp.choices[0].message.content or ""
            completion_text = choice
            model_name = resp.model or PROVIDER_MODEL
            last_error = None
            break
        except (APIStatusError, APIConnectionError) as exc:
            last_error = exc
            retryable = _retryable(exc)
            if not retryable or attempt >= MAX_ATTEMPTS:
                break
            delay = BACKOFF_MS[min(attempt - 1, len(BACKOFF_MS) - 1)] / 1000.0
            delay += random.uniform(0, 0.05)
            time.sleep(delay)

    if last_error is not None:
        raise HTTPException(status_code=502, detail=f"provider failed after retries: {last_error}")

    _persist(body.request_id, body.item_id, completion_text, model_name)
    return GenerateResponse(result=completion_text, model=model_name, status="ok")


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, APIConnectionError):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in {429, 503}
    return False


def _read_existing(request_id: str) -> dict[str, Any] | None:
    with psycopg.connect(DB_DSN, connect_timeout=2) as conn:
        row = conn.execute(
            "SELECT result_text, model_name FROM recommendations WHERE request_id = %s",
            (request_id,),
        ).fetchone()
    if row is None:
        return None
    return {"result": row[0], "model": row[1]}


def _persist(request_id: str, item_id: str, result: str, model: str) -> None:
    with psycopg.connect(DB_DSN, connect_timeout=2) as conn:
        conn.execute(
            """
            INSERT INTO recommendations (request_id, item_id, result_text, model_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (request_id) DO NOTHING
            """,
            (request_id, item_id, result, model),
        )
        conn.commit()
